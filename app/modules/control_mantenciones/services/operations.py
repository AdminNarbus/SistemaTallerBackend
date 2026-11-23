"""Casos de uso de mantenciones, kilometrajes y bitácora."""

from typing import Any

from datetime import date
from decimal import Decimal

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleException,
    ConflictException,
    NotFoundException,
)
from app.modules.buses.models.bus import Bus
from app.modules.control_mantenciones.models.entities import (
    ControlEvento as Evento,
    ControlKilometraje as Km,
    ControlMantencion as Mant,
)
from app.modules.control_mantenciones.repository.records import RecordsRepository
from app.modules.control_mantenciones.services.domain import (
    hoy,
    motivos_secuencia,
)
from app.modules.control_mantenciones.services.transactions import atomic
from app.modules.control_mantenciones.dtos.contracts import (
    Comentario,
    Decision,
    IntervaloEditar,
    LecturaCrear,
    LecturaEditar,
    MantencionCrear,
    MantencionEditar,
)


from app.modules.control_mantenciones.dtos.serialization import snapshot


class OperationsService:
    def __init__(self, db: AsyncSession, actor_id: int) -> Any:
        self.db, self.actor_id = db, actor_id
        self.repo = RecordsRepository()

    async def requerido(self, modelo: Any, identificador: int) -> Any:
        registro = await self.repo.obtener(self.db, modelo, identificador)
        if registro is None:
            raise NotFoundException("No se encontró el registro solicitado.")
        return registro

    async def bus(self, bus_id: int) -> Any:
        bus = await self.requerido(Bus, bus_id)
        if not bus.is_active or not bus.n_bus:
            raise BusinessRuleException(
                "Seleccione un bus activo con número de máquina."
            )
        return bus

    def verificar_version(self, registro: Any, version: int) -> None:
        if registro.version != version:
            raise ConflictException("El registro cambió. Recargue antes de editar.")

    async def evento(self, tipo: str, datos: dict) -> Any:
        registro = Evento(tipo=tipo, usuario_id=self.actor_id, **datos)
        return await self.repo.agregar(self.db, registro)

    @atomic
    async def crear_mantencion(self, datos: MantencionCrear) -> dict:
        if datos.kilometraje is not None and datos.fecha is None:
            raise BusinessRuleException("Indique la fecha de la mantención para registrar su kilometraje.")
        await self.bus(datos.bus_id)
        valores = datos.model_dump()
        valores["estado"] = "incompleta"
        registro = Mant(
            **valores,
            usuario_creacion_id=self.actor_id,
            usuario_actualizacion_id=self.actor_id
        )
        await self.repo.agregar(self.db, registro)
        await self.evento(
            "mantencion_creada",
            {
                "bus_id": registro.bus_id,
                "mantencion_id": registro.id,
                "valores_nuevos": snapshot(registro),
            },
        )
        return snapshot(registro)

    @atomic
    async def editar_mantencion(
        self, identificador: int, datos: MantencionEditar
    ) -> dict:
        registro = await self.requerido(Mant, identificador)
        await self.bus(registro.bus_id)
        self.verificar_version(registro, datos.version)
        anterior = snapshot(registro)
        cambios = datos.model_dump(exclude_unset=True, exclude={"version"})
        if (
            {"fecha", "kilometraje"} & cambios.keys()
            and cambios.get("kilometraje", registro.kilometraje) is not None
            and cambios.get("fecha", registro.fecha) is None
        ):
            raise BusinessRuleException(
                "Indique la fecha de la mantención para registrar su kilometraje."
            )
        if (
            cambios.get("estado", registro.estado) is None
            or cambios.get("activa", registro.activa) is None
        ):
            raise BusinessRuleException("Estado y vigencia no pueden quedar vacíos.")
        for campo, valor in cambios.items():
            setattr(registro, campo, valor)
        registro.version += 1
        registro.usuario_actualizacion_id = self.actor_id
        await self.db.flush()
        await self.evento(
            "mantencion_editada",
            {
                "bus_id": registro.bus_id,
                "mantencion_id": registro.id,
                "valores_anteriores": anterior,
                "valores_nuevos": snapshot(registro),
            },
        )
        return snapshot(registro)

    @atomic
    async def eliminar_mantencion(self, identificador: int, version: int) -> Any:
        registro = await self.requerido(Mant, identificador)
        await self.bus(registro.bus_id)
        self.verificar_version(registro, version)
        await self.evento(
            "mantencion_eliminada",
            {"bus_id": registro.bus_id, "valores_anteriores": snapshot(registro)},
        )
        await self.repo.eliminar(self.db, registro)

    @atomic
    async def eliminar_lectura(self, identificador: int, version: int) -> None:
        registro = await self.requerido(Km, identificador)
        self.verificar_version(registro, version)
        await self.evento(
            "kilometraje_eliminado",
            {"bus_id": registro.bus_id, "valores_anteriores": snapshot(registro)},
        )
        await self.repo.eliminar(self.db, registro)

    @atomic
    async def comentar(self, identificador: int, datos: Comentario) -> dict:
        registro = await self.requerido(Mant, identificador)
        texto = datos.comentario.strip()
        if not texto:
            raise BusinessRuleException("El comentario no puede quedar vacío.")
        evento = await self.evento(
            "comentario",
            {
                "bus_id": registro.bus_id,
                "mantencion_id": registro.id,
                "comentario": texto,
            },
        )
        return snapshot(evento)

    @atomic
    async def intervalo(self, identificador: int, datos: IntervaloEditar) -> dict:
        bus = await self.bus(identificador)
        version = await self.repo.version_intervalo(self.db, identificador)
        if datos.version != version:
            raise ConflictException("El intervalo cambió. Recargue la ficha del bus.")
        anterior = bus.intervalo_mantencion_km
        bus.intervalo_mantencion_km = datos.intervalo_mantencion_km
        evento = await self.evento(
            "intervalo_cambiado",
            {
                "bus_id": identificador,
                "valores_anteriores": {
                    "intervalo": str(anterior) if anterior is not None else None
                },
                "valores_nuevos": {
                    "intervalo": (
                        str(bus.intervalo_mantencion_km)
                        if bus.intervalo_mantencion_km is not None
                        else None
                    )
                },
            },
        )
        return {
            "intervalo_mantencion_km": bus.intervalo_mantencion_km,
            "version": evento.id,
        }

    async def evaluar(
        self, lectura: dict, excluir: int | None = None
    ) -> tuple[str, list[str]]:
        contexto = (await self.repo.contexto(self.db, [lectura], excluir)).get(0, {})
        mapeado = {
            "anterior": (
                {
                    "fecha": contexto.get("anterior_fecha"),
                    "kilometraje": contexto.get("anterior_km"),
                }
                if contexto.get("anterior_fecha")
                else None
            ),
            "posterior": (
                {"kilometraje": contexto.get("posterior_km")}
                if contexto.get("posterior_fecha")
                else None
            ),
            "misma_fecha_distinta": any(
                k != lectura["kilometraje"] for k in contexto.get("mismos") or []
            ),
        }
        motivos = motivos_secuencia(lectura["fecha"], lectura["kilometraje"], mapeado)
        if lectura["fecha"] is None:
            motivos.append("Fecha inválida o incompleta.")
        elif lectura["fecha"] > hoy():
            motivos.append("Fecha futura.")
        if not lectura["bus_id"]:
            motivos.append("Bus desconocido.")
        duplicados = await self.repo.duplicados(self.db, [lectura], excluir)
        if (lectura["bus_id"], lectura["fecha"], lectura["kilometraje"]) in duplicados:
            raise ConflictException(
                "Ya existe una lectura aceptada con esa fecha y kilometraje."
            )
        return ("pendiente" if motivos else "aceptado"), motivos

    @atomic
    async def crear_lectura(self, datos: LecturaCrear) -> dict:
        bus = await self.bus(datos.bus_id)
        if datos.fecha > hoy():
            raise BusinessRuleException("La fecha no puede ser futura.")
        estado, motivos = await self.evaluar(datos.model_dump())
        registro = Km(
            **datos.model_dump(),
            numero_bus_origen=bus.n_bus,
            origen="manual",
            estado=estado,
            observaciones=motivos,
            datos_origen={},
            usuario_creacion_id=self.actor_id,
            usuario_actualizacion_id=self.actor_id
        )
        await self.repo.agregar(self.db, registro)
        await self.evento(
            "kilometraje_creado",
            {
                "bus_id": bus.id,
                "kilometraje_id": registro.id,
                "valores_nuevos": snapshot(registro),
            },
        )
        return snapshot(registro)

    async def resolver_bus_lectura(self, registro: Any) -> None:
        if registro.bus_id is None and registro.numero_bus_origen:
            buses = await self.repo.buses(self.db, [registro.numero_bus_origen])
            if buses:
                registro.bus_id = buses[0].id
        if registro.bus_id:
            await self.bus(registro.bus_id)

    @atomic
    async def editar_lectura(self, identificador: int, datos: LecturaEditar) -> dict:
        registro = await self.requerido(Km, identificador)
        await self.resolver_bus_lectura(registro)
        self.verificar_version(registro, datos.version)
        anterior = snapshot(registro)
        cambios = datos.model_dump(exclude_unset=True, exclude={"version"})
        valores = {
            "bus_id": registro.bus_id,
            "fecha": cambios.get("fecha", registro.fecha),
            "kilometraje": cambios.get("kilometraje", registro.kilometraje),
        }
        if valores["kilometraje"] is None:
            raise BusinessRuleException("Ingrese un kilometraje válido.")
        registro.estado, registro.observaciones = await self.evaluar(
            valores, registro.id
        )
        for campo, valor in cambios.items():
            setattr(registro, campo, valor)
        registro.version += 1
        registro.usuario_actualizacion_id = self.actor_id
        await self.db.flush()
        await self.evento(
            "kilometraje_editado",
            {
                "bus_id": registro.bus_id,
                "kilometraje_id": registro.id,
                "valores_anteriores": anterior,
                "valores_nuevos": snapshot(registro),
            },
        )
        return snapshot(registro)

    @atomic
    async def decidir(self, identificador: int, datos: Decision) -> dict:
        registro = await self.requerido(Km, identificador)
        await self.resolver_bus_lectura(registro)
        self.verificar_version(registro, datos.version)
        anterior = snapshot(registro)
        if datos.accion == "aceptar":
            if (
                not registro.bus_id
                or not registro.fecha
                or registro.fecha > hoy()
                or registro.kilometraje is None
                or registro.kilometraje < 0
            ):
                raise BusinessRuleException(
                    "Complete bus, fecha y kilometraje válidos antes de aceptar."
                )
            await self.evaluar(
                {
                    "bus_id": registro.bus_id,
                    "fecha": registro.fecha,
                    "kilometraje": registro.kilometraje,
                },
                registro.id,
            )
        registro.estado = "aceptado" if datos.accion == "aceptar" else "excluido"
        registro.version += 1
        registro.usuario_actualizacion_id = self.actor_id
        await self.db.flush()
        await self.evento(
            "decision",
            {
                "bus_id": registro.bus_id,
                "kilometraje_id": registro.id,
                "valores_anteriores": anterior,
                "valores_nuevos": snapshot(registro),
            },
        )
        return snapshot(registro)
