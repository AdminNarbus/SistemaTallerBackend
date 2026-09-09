import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.neumaticos.dtos.reporte_neumatico_dto import (
    FormularioNeumaticoResponseDTO,
    FormularioNeumaticoStatusDTO,
    ReporteNeumaticoCreateDTO,
    ReporteNeumaticoResponseDTO,
)
from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico
from app.modules.neumaticos.repository.neumatico_repository import neumatico_repository

UPLOAD_EVIDENCIAS_DIR = os.path.join(os.getcwd(), "uploads", "evidencias")

logger = logging.getLogger(__name__)


def _guardar_archivo_disco(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


class FormularioNeumaticoService:
    """
    Capa de Servicio (Cerebro del Negocio / Casos de Uso) para el módulo de Neumáticos.
    Responsabilidades:
    - Validación de reglas de negocio y parseo seguro de entradas.
    - Orquestación de pasos (evidencias, resolución de vehículos y persistencia).
    - Gobierno exclusivo de la transacción de BD (decide cuándo hacer commit() y rollback()).
    - Uso estricto de excepciones de dominio (BusinessRuleException, NotFoundException).
    """

    async def obtener_estado_formulario(self) -> FormularioNeumaticoStatusDTO:
        """Retorna el estado de disponibilidad del formulario de neumáticos."""
        return FormularioNeumaticoStatusDTO()

    async def procesar_formulario(
        self,
        dto: Optional[ReporteNeumaticoCreateDTO] = None,
        evidencia: Optional[UploadFile] = None,
        usuario_id: Optional[int] = None,
        db: Optional[AsyncSession] = None,
        **kwargs: Any,
    ) -> FormularioNeumaticoResponseDTO:
        """
        Orquesta el procesamiento del formulario de neumáticos.
        Acepta tanto un DTO tipado como argumentos kwargs para compatibilidad total con tests existentes.
        """
        # 1. Normalización de entrada DTO / kwargs
        if dto is None:
            dto = ReporteNeumaticoCreateDTO(
                usuario_id=usuario_id or kwargs.get("usuario_id"),
                maquina=kwargs.get("maquina"),
                tipo_bus=kwargs.get("tipo_bus"),
                ruedas=kwargs.get("ruedas"),
                motivo=kwargs.get("motivo"),
                precio=kwargs.get("precio"),
                marca_fuego=kwargs.get("marca_fuego"),
            )

        if evidencia is None and "evidencia" in kwargs:
            evidencia = kwargs.get("evidencia")

        if db is None and "db" in kwargs:
            db = kwargs.get("db")

        effective_user_id = usuario_id if usuario_id is not None else dto.usuario_id

        logger.info(
            "[NEUMATICO] Iniciando procesamiento de formulario | usuario_id=%s | maquina='%s' | tipo_bus='%s'",
            effective_user_id,
            dto.maquina,
            dto.tipo_bus,
        )

        # 2. Manejo de evidencia fotográfica (I/O asíncrono no bloqueante)
        evidencia_url: Optional[str] = None
        nombre_original_evidencia = "Sin evidencia adjunta"

        if evidencia and evidencia.filename:
            nombre_original_evidencia = evidencia.filename
            extension = (os.path.splitext(evidencia.filename)[1] or ".jpg").lower()

            extensiones_permitidas = {".jpg", ".jpeg", ".png", ".webp"}
            if extension not in extensiones_permitidas:
                raise BusinessRuleException(
                    f"Tipo de archivo no permitido: '{extension}'. Extensiones válidas: {', '.join(sorted(extensiones_permitidas))}"
                )

            contenido = await evidencia.read()

            max_tamano_bytes = 10 * 1024 * 1024  # 10 MB
            if len(contenido) > max_tamano_bytes:
                raise BusinessRuleException(
                    f"El archivo supera el tamaño máximo permitido de {max_tamano_bytes // (1024 * 1024)} MB."
                )

            nombre_archivo_unico = f"{uuid.uuid4()}{extension}"
            ruta_destino = os.path.join(UPLOAD_EVIDENCIAS_DIR, nombre_archivo_unico)

            os.makedirs(UPLOAD_EVIDENCIAS_DIR, exist_ok=True)
            await asyncio.to_thread(_guardar_archivo_disco, ruta_destino, contenido)

            evidencia_url = f"/uploads/evidencias/{nombre_archivo_unico}"
            logger.info(
                "[NEUMATICO] Evidencia fotográfica guardada con éxito | archivo='%s' | tamaño=%s bytes",
                nombre_archivo_unico,
                len(contenido),
            )

        # 3. Parseo y validación de ruedas y precio
        ruedas_lista = dto.ruedas
        if isinstance(dto.ruedas, str):
            try:
                ruedas_lista = json.loads(dto.ruedas)
            except Exception:
                pass

        precio_float: Optional[float] = None
        if dto.precio is not None:
            if isinstance(dto.precio, (int, float)):
                precio_float = float(dto.precio)
            else:
                try:
                    precio_limpio = str(dto.precio).replace(".", "").replace(",", ".")
                    precio_float = float(precio_limpio)
                except Exception:
                    precio_float = None

        # 4. Orquestación de Persistencia y Control de Transacción
        reporte_id: Optional[int] = None
        bus_id: Optional[int] = dto.bus_id

        if db is not None:
            # 4.1 Resolución atómica de bus por máquina si no viene el bus_id
            if not bus_id and dto.maquina:
                bus = await neumatico_repository.get_bus_by_numero(db, dto.maquina)
                if bus:
                    bus_id = bus.id

            # 4.2 Instanciación del modelo de dominio
            reporte = ReporteNeumatico(
                usuario_id=effective_user_id,
                bus_id=bus_id,
                n_bus=dto.maquina,
                tipo_bus=dto.tipo_bus,
                ruedas=ruedas_lista,
                motivo=dto.motivo,
                precio=precio_float,
                marca_fuego=dto.marca_fuego,
                evidencia_url=evidencia_url,
                fecha_subida=datetime.now(timezone.utc),
            )

            # 4.3 Persistencia atómica vía repositorio
            await neumatico_repository.add(db, reporte)

            # 4.4 Gobierno de Transacción en la capa de Servicio
            try:
                await db.commit()
                await db.refresh(reporte)
                reporte_id = reporte.id
                bus_id = reporte.bus_id
                logger.info(
                    "[NEUMATICO] Reporte persistido y commiteado exitosamente | id=%s | n_bus='%s' | bus_id=%s",
                    reporte_id,
                    dto.maquina,
                    bus_id,
                )
            except Exception as err:
                await db.rollback()
                logger.error(
                    "[NEUMATICO] Error crítico en commit de reporte | usuario_id=%s | error=%s",
                    effective_user_id,
                    err,
                    exc_info=True,
                )
                raise BusinessRuleException("Error al registrar el reporte de neumáticos en la base de datos.")

        # 5. Generación de resumen y retorno del DTO
        resumen_procesamiento = (
            f"Datos recibidos del formulario: "
            f"UsuarioID={effective_user_id or 'N/A'}, "
            f"Máquina='{dto.maquina or 'N/A'}', "
            f"BusID={bus_id or 'N/A'}, "
            f"Tipo de Bus='{dto.tipo_bus or 'N/A'}', "
            f"Ruedas={ruedas_lista or '[]'}, "
            f"Motivo='{dto.motivo or 'N/A'}', "
            f"Precio='{dto.precio or 'N/A'}', "
            f"Marca de Fuego='{dto.marca_fuego or 'N/A'}', "
            f"Evidencia Guardada='{evidencia_url or 'N/A'}'"
        )

        datos_recibidos = {
            "usuario_id": effective_user_id,
            "maquina": dto.maquina,
            "bus_id": bus_id,
            "tipo_bus": dto.tipo_bus,
            "ruedas": ruedas_lista,
            "motivo": dto.motivo,
            "precio": str(dto.precio) if dto.precio is not None else None,
            "marca_fuego": dto.marca_fuego,
            "evidencia_original": nombre_original_evidencia,
            "evidencia_url": evidencia_url,
        }

        return FormularioNeumaticoResponseDTO(
            status="success",
            message="Formulario de neumáticos procesado y guardado exitosamente",
            reporte_id=reporte_id,
            bus_id=bus_id,
            resumen=resumen_procesamiento,
            datos_recibidos=datos_recibidos,
        )

    async def get_reporte_by_id(
        self, db: AsyncSession, reporte_id: int
    ) -> ReporteNeumaticoResponseDTO:
        """Obtiene un reporte de neumático por ID o lanza NotFoundException."""
        reporte = await neumatico_repository.get_by_id(db, reporte_id)
        if not reporte:
            raise NotFoundException(f"Reporte de neumático {reporte_id} no encontrado")
        return ReporteNeumaticoResponseDTO.model_validate(reporte)


formulario_neumatico_service = FormularioNeumaticoService()
