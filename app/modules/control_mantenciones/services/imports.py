"""Revisión sin persistencia y confirmación transaccional de cargas."""

from typing import Any

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select

from app.core.exceptions import BusinessRuleException, ConflictException
from app.modules.control_mantenciones.dtos.contracts import (
    Borrador,
    FilaBorrador,
    ResultadoFila,
    Revision,
)
from app.modules.control_mantenciones.models.entities import (
    ControlEvento as Evento,
    ControlKilometraje as Km,
)
from app.modules.control_mantenciones.services.domain import (
    fecha_valida,
    hoy,
    motivo_aumento_excesivo,
    motivos_secuencia,
    numero,
)
from app.modules.control_mantenciones.services.operations import (
    OperationsService,
    snapshot,
)
from app.modules.control_mantenciones.services.transactions import atomic

MAX_BYTES = 20 * 1024 * 1024
MAX_EXPANDIDO = 200 * 1024 * 1024
MAX_FILAS = 100000
def leer_excel(nombre: str, contenido: bytes) -> Borrador:
    """Interpreta el documento en un hilo; no escribe archivos ni filas en BD."""
    from openpyxl import load_workbook

    if (
        not nombre.lower().endswith(".xlsx")
        or not contenido
        or len(contenido) > MAX_BYTES
    ):
        raise BusinessRuleException("Seleccione un Excel .xlsx de hasta 20 MB.")
    try:
        with ZipFile(BytesIO(contenido)) as archivo:
            if (
                sum(i.file_size for i in archivo.infolist()) > MAX_EXPANDIDO
                or "xl/workbook.xml" not in archivo.namelist()
            ):
                raise BusinessRuleException(
                    "El Excel excede los límites de procesamiento o no tiene una estructura válida."
                )
        libro = load_workbook(
            BytesIO(contenido), read_only=True, data_only=True, keep_links=False
        )
    except (BadZipFile, ValueError, KeyError, OSError) as error:
        raise BusinessRuleException(
            "No se pudo leer el Excel. Compruebe su formato."
        ) from error
    try:
        return extraer_filas(libro, nombre)
    finally:
        libro.close()


def extraer_filas(libro: Any, nombre: str) -> Borrador:
    if "Query result" not in libro.sheetnames:
        raise BusinessRuleException("El Excel debe contener la hoja Query result.")
    hoja = libro["Query result"]
    if hoja.max_row > MAX_FILAS + 1 or hoja.max_column > 500:
        raise BusinessRuleException(
            "El Excel excede el máximo de filas o columnas permitido."
        )
    iterador = hoja.iter_rows(values_only=True)
    encabezados = [str(c or "").strip() for c in next(iterador, [])]
    obligatorias = ("n_bus", "fecha", "odometro")
    if any(encabezados.count(c) != 1 for c in obligatorias):
        raise BusinessRuleException(
            "Se requieren las columnas únicas n_bus, fecha y odometro."
        )
    indices = {c: encabezados.index(c) for c in obligatorias}
    filas = []
    for posicion, valores in enumerate(iterador, start=2):
        if posicion > MAX_FILAS + 1:
            raise BusinessRuleException("El Excel excede el máximo de filas permitido.")
        dato = {c: valores[i] if i < len(valores) else None for c, i in indices.items()}
        filas.append(
            FilaBorrador(
                fila=posicion,
                numero_bus=texto(dato["n_bus"]),
                fecha=fecha_excel(dato["fecha"], libro.epoch),
                kilometraje=texto(dato["odometro"]),
            )
        )
    if not filas:
        raise BusinessRuleException("El Excel no contiene lecturas.")
    return Borrador(nombre_archivo=nombre, filas=filas)


def texto(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()[:100]


def fecha_excel(valor: Any, epoch: Any) -> str | None:
    from openpyxl.utils.datetime import from_excel

    if isinstance(valor, (date, datetime)):
        return valor.isoformat()[:10]
    if isinstance(valor, (float, int)) and 0 < valor < 100000:
        return from_excel(valor, epoch).isoformat()[:10]
    cadena = texto(valor)
    for formato in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(cadena or "", formato).date().isoformat()
        except ValueError:
            continue
    return cadena


class ImportService(OperationsService):
    async def revisar(self, borrador: Borrador, excluir: int | None = None) -> Revision:
        contexto = await self.contexto_revision(borrador, excluir)
        resultados = [self.resultado(fila, contexto) for fila in borrador.filas]
        resumen = dict(Counter(r.estado for r in resultados))
        desconocidos = {
            f.numero_bus
            for f in borrador.filas
            if f.numero_bus and f.numero_bus not in contexto["buses"]
        }
        resumen.update(leidas=len(resultados), desconocidos=len(desconocidos))
        return Revision(borrador=borrador, resultados=resultados, resumen=resumen)

    def seleccionar(self, filas: list[FilaBorrador]) -> list[FilaBorrador]:
        grupos = {}
        for fila in filas:
            clave = fila.numero_bus or f"sin_bus:{fila.id}"
            grupos.setdefault(clave, []).append(fila)
        return [
            sorted(
                grupo,
                key=lambda f: (
                    fecha_valida(f.fecha) is None,
                    -(fecha_valida(f.fecha) or date.min).toordinal(),
                    f.fila,
                ),
            )[0]
            for grupo in grupos.values()
        ]

    def resultado(self, fila: Any, contexto: Any) -> ResultadoFila:
        bus_id = contexto["buses"].get(fila.numero_bus)
        fecha, km = fecha_valida(fila.fecha), numero(fila.kilometraje)
        indice = contexto["indices"].get(fila.id)
        referencia = contexto["contextos"].get(indice, {})
        anterior = (
            {
                "fecha": referencia["anterior_fecha"],
                "kilometraje": referencia["anterior_km"],
            }
            if referencia.get("anterior_fecha")
            else None
        )
        estado, motivos = self.estado_basico(fila, indice)
        if estado is None:
            motivos = self.advertencias(
                fila, bus_id, fecha, km, referencia, contexto["por_fecha"]
            )
            estado = "pendiente" if motivos else "aceptado"
            if (bus_id, fecha, km) in contexto["duplicados"]:
                estado, motivos = "duplicado", [
                    "La lectura ya existe en el historial confirmado."
                ]
        return ResultadoFila(
            fila=fila,
            bus_id=bus_id,
            estado=estado,
            motivos=motivos,
            anterior=anterior,
            seleccionada=indice is not None,
        )

    def advertencias(
        self, fila: Any, bus_id: Any, fecha: Any, km: Any, contexto: Any, filas: Any
    ) -> list[str]:
        motivos = []
        if fecha is None:
            motivos.append("Fecha inválida o incompleta.")
        elif fecha > hoy():
            motivos.append("Fecha futura.")
        if not bus_id:
            motivos.append(
                "Bus desconocido: registre la ficha en el catálogo del taller."
            )
        referencia = {
            "anterior": (
                {"kilometraje": contexto["anterior_km"]}
                if contexto.get("anterior_fecha")
                else None
            ),
            "posterior": (
                {"kilometraje": contexto["posterior_km"]}
                if contexto.get("posterior_fecha")
                else None
            ),
            "misma_fecha_distinta": any(k != km for k in contexto.get("mismos") or []),
        }
        motivos.extend(motivos_secuencia(fecha, km, referencia))
        motivo_aumento = motivo_aumento_excesivo(fecha, km, contexto)
        if motivo_aumento:
            motivos.append(motivo_aumento)
        if fecha and len(filas.get((fila.numero_bus, fecha), set())) > 1:
            motivos.append("Hay kilometrajes distintos en la misma fecha del archivo.")
        return motivos

    @atomic
    async def confirmar(self, borrador: Borrador) -> dict:
        await self.repo.bloquear_clave(self.db, borrador.clave_operacion)
        existente = await self.repo.carga_por_clave(self.db, borrador.clave_operacion)
        if existente:
            if existente.metadatos.get("firma") != self.firma(borrador):
                raise ConflictException(
                    "La clave de operación ya se utilizó con otros datos."
                )
            return existente.metadatos["respuesta"]
        buses = await self.repo.buses(
            self.db, list({f.numero_bus for f in borrador.filas if f.numero_bus})
        )
        await self.repo.bloquear_buses(self.db, [b.id for b in buses])
        revision = await self.revisar(borrador)
        return await self.persistir_carga(revision)

    def firma(self, borrador: Borrador) -> str:
        import hashlib

        return hashlib.sha256(borrador.model_dump_json().encode()).hexdigest()

    def registro_confirmado(self, resultado: ResultadoFila, carga_id: int) -> Km:
        fila, km = resultado.fila, numero(resultado.fila.kilometraje)
        estado = self.estado_confirmado(resultado)
        valido = (
            km is not None
            and km >= 0
            and km < Decimal("10000000000")
            and km.as_tuple().exponent >= -2
        )
        datos = {
            "bus_id": resultado.bus_id,
            "numero_bus_origen": fila.numero_bus,
            "fecha": fecha_valida(fila.fecha),
            "kilometraje": km if valido else None,
            "estado": estado,
            "origen": "excel",
            "evento_carga_id": carga_id,
            "fila_origen": fila.fila,
            "datos_origen": fila.model_dump(mode="json"),
            "observaciones": resultado.motivos,
            "usuario_creacion_id": self.actor_id,
            "usuario_actualizacion_id": self.actor_id,
        }
        return Km(**datos)

    @atomic
    async def eliminar_carga(self, identificador: int) -> None:
        carga = await self.requerido(Evento, identificador)
        if carga.tipo != "carga_confirmada":
            raise BusinessRuleException(
                "El evento no corresponde a una carga de Excel."
            )
        registros = await self.repo.registros_carga(self.db, carga.id)
        await self.repo.bloquear_buses(
            self.db, sorted({r.bus_id for r in registros if r.bus_id})
        )
        ids = [r.id for r in registros]
        await self.repo.borrar_eventos_lecturas(self.db, ids)
        await self.repo.eliminar_lecturas_carga(self.db, carga.id)
        await self.repo.eliminar(self.db, carga)

    async def contexto_revision(self, borrador: Borrador, excluir: int | None) -> dict:
        if len({f.id for f in borrador.filas}) != len(borrador.filas):
            raise BusinessRuleException(
                "La revisión contiene identificadores de fila repetidos."
            )
        numeros = list({f.numero_bus for f in borrador.filas if f.numero_bus})
        buses = {b.n_bus: b.id for b in await self.repo.buses(self.db, numeros)}
        seleccionadas = self.seleccionar(borrador.filas)
        candidatos = [
            {
                "bus_id": buses.get(f.numero_bus),
                "fecha": fecha_valida(f.fecha),
                "kilometraje": numero(f.kilometraje),
            }
            for f in seleccionadas
        ]
        contextos, duplicados = await self.contextos_por_bloques(candidatos, excluir)
        por_fecha = {}
        for fila in borrador.filas:
            por_fecha.setdefault(
                (fila.numero_bus, fecha_valida(fila.fecha)), set()
            ).add(numero(fila.kilometraje))
        return {
            "buses": buses,
            "indices": {f.id: i for i, f in enumerate(seleccionadas)},
            "contextos": contextos,
            "duplicados": duplicados,
            "por_fecha": por_fecha,
        }

    async def contextos_por_bloques(
        self, candidatos: list[dict], excluir: int | None
    ) -> tuple:
        contextos, duplicados = {}, set()
        for inicio in range(0, len(candidatos), 500):
            bloque = candidatos[inicio : inicio + 500]
            contextos.update(
                {
                    inicio + i: c
                    for i, c in (
                        await self.repo.contexto(self.db, bloque, excluir)
                    ).items()
                }
            )
            duplicados.update(await self.repo.duplicados(self.db, bloque, excluir))
        return contextos, duplicados

    def estado_basico(self, fila: Any, indice: Any) -> tuple:
        km = numero(fila.kilometraje)
        if (
            not fila.numero_bus
            or fila.kilometraje is None
            or not fila.kilometraje.strip()
        ):
            return "ignorado", ["Falta el número de bus o el odómetro."]
        if (
            not fila.numero_bus.isdecimal()
            or int(fila.numero_bus) <= 0
            or km is None
            or km < 0
            or km >= Decimal("10000000000")
            or km.as_tuple().exponent < -2
        ):
            return "error", [
                "Número de bus u odómetro inválido, negativo o fuera de rango."
            ]
        if indice is None:
            return "ignorado", [
                "Lectura anterior omitida; solo se considera la más reciente del archivo."
            ]
        return None, []

    def estado_confirmado(self, resultado: ResultadoFila) -> str:
        if resultado.estado == "duplicado":
            return "excluido"
        if resultado.estado != "pendiente":
            return resultado.estado
        fila = resultado.fila
        if fila.decision == "aceptar":
            fecha, km = fecha_valida(fila.fecha), numero(fila.kilometraje)
            if (
                not resultado.bus_id
                or not fecha
                or fecha > hoy()
                or km is None
                or km < 0
            ):
                raise BusinessRuleException(
                    f"Fila {fila.fila}: complete bus, fecha y kilometraje válidos antes de aceptar."
                )
            return "aceptado"
        return "excluido" if fila.decision == "excluir" else "pendiente"

    async def persistir_carga(self, revision: Revision) -> dict:
        borrador = revision.borrador
        carga = await self.evento(
            "carga_confirmada",
            {
                "clave_operacion": borrador.clave_operacion,
                "metadatos": {"nombre_archivo": borrador.nombre_archivo},
            },
        )
        registros = [
            self.registro_confirmado(r, carga.id)
            for r in revision.resultados
            if r.seleccionada
        ]
        await self.repo.agregar_lote(self.db, registros)
        respuesta = {
            "carga_id": carga.id,
            "resumen": dict(Counter(r.estado for r in registros)),
            "buses_afectados": sorted({r.bus_id for r in registros if r.bus_id}),
        }
        carga.metadatos = {
            "nombre_archivo": borrador.nombre_archivo,
            "firma": self.firma(borrador),
            "revision": revision.model_dump(mode="json"),
            "respuesta": respuesta,
        }
        return respuesta
