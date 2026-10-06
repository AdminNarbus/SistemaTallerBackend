import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.core.storage.storage_service import storage_service
from app.modules.formularios.dtos.neumaticos_dto import (
    FormularioNeumaticoResponseDTO,
    FormularioNeumaticoStatusDTO,
    ReporteNeumaticoCreateDTO,
    ReporteNeumaticoPaginadoDTO,
    ReporteNeumaticoResponseDTO,
)
from app.modules.formularios.repository.neumatico_repository import (
    NeumaticoRepository,
    neumatico_repository,
)
from app.modules.formularios.models.reporte_neumatico import ReporteNeumatico

logger = logging.getLogger(__name__)


class FormularioNeumaticoService:
    """
    Capa de Servicio (Cerebro del Negocio / Casos de Uso) para el formulario de Neumáticos.
    Responsabilidades:
    - Validación de reglas de negocio y parseo seguro de entradas.
    - Orquestación de pasos (evidencias, resolución de vehículos y persistencia).
    - Gobierno exclusivo de la transacción de BD (decide cuándo hacer commit() y rollback()).
    - Uso estricto de excepciones de dominio (BusinessRuleException, NotFoundException).
    - Inyección de dependencias para desacoplamiento y testing unitario aislado.
    """

    def __init__(
        self,
        repository: Optional[NeumaticoRepository] = None,
        storage_srv: Optional[Any] = None,
    ):
        self.repository = repository or neumatico_repository
        self.storage_service = storage_srv or storage_service

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
                ruedas=kwargs.get("ruedas"),
                motivo=kwargs.get("motivo"),
                marca_fuego=kwargs.get("marca_fuego"),
            )

        if evidencia is None and "evidencia" in kwargs:
            evidencia = kwargs.get("evidencia")

        if db is None and "db" in kwargs:
            db = kwargs.get("db")

        effective_user_id = usuario_id if usuario_id is not None else dto.usuario_id

        logger.info(
            "[NEUMATICO] Iniciando procesamiento de formulario | usuario_id=%s | maquina='%s'",
            effective_user_id,
            dto.maquina,
        )

        # 2. Manejo de evidencia fotográfica mediante StorageService (GCS o Local)
        evidencia_url: Optional[str] = None
        evidencia_path: Optional[str] = None
        nombre_original_evidencia = "Sin evidencia adjunta"

        if evidencia and evidencia.filename:
            nombre_original_evidencia = evidencia.filename
            resultado_upload = await self.storage_service.upload_image(
                file=evidencia,
                folder="evidencias",
            )
            evidencia_path = resultado_upload.get("path") or resultado_upload["url"]
            evidencia_url = resultado_upload["url"]
            logger.info(
                "[NEUMATICO] Evidencia fotográfica guardada con éxito | path='%s' | url='%s' | tamaño=%s bytes",
                evidencia_path,
                evidencia_url,
                resultado_upload["size_bytes"],
            )

        # El DTO garantiza exactamente un neumático antes de subir evidencias.
        ruedas_lista = dto.ruedas

        # 4. Orquestación de Persistencia y Control de Transacción
        reporte_id: Optional[int] = None
        bus_id: Optional[int] = dto.bus_id
        tipo_bus_resuelto: Optional[str] = None

        if db is not None:
            # 4.1 Resolución atómica de bus por máquina si no viene el bus_id
            if not bus_id and dto.maquina:
                bus = await self.repository.get_bus_by_numero(db, dto.maquina)
                if bus:
                    bus_id = bus.id
                    tipo_bus_resuelto = bus.tipo_bus

            # 4.2 Instanciación del modelo de dominio (monto/precio eliminado, tipo_bus autocompletado si existe)
            reporte = ReporteNeumatico(
                usuario_id=effective_user_id,
                bus_id=bus_id,
                n_bus=dto.maquina,
                tipo_bus=tipo_bus_resuelto,
                ruedas=ruedas_lista,
                motivo=dto.motivo,
                marca_fuego=dto.marca_fuego,
                evidencia_url=evidencia_path,
                fecha_subida=datetime.now(timezone.utc),
            )

            # 4.3 Persistencia atómica vía repositorio
            await self.repository.add(db, reporte)

            # 4.4 Gobierno de Transacción en la capa de Servicio
            try:
                await db.commit()
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
            f"Ruedas={ruedas_lista or '[]'}, "
            f"Motivo='{dto.motivo or 'N/A'}', "
            f"Marca de Fuego='{dto.marca_fuego or 'N/A'}', "
            f"Evidencia Guardada='{evidencia_url or 'N/A'}'"
        )

        datos_recibidos = {
            "usuario_id": effective_user_id,
            "maquina": dto.maquina,
            "bus_id": bus_id,
            "ruedas": ruedas_lista,
            "motivo": dto.motivo,
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
        reporte = await self.repository.get_by_id(db, reporte_id)
        if not reporte:
            raise NotFoundException(f"Reporte de neumático {reporte_id} no encontrado")
        dto = ReporteNeumaticoResponseDTO.model_validate(reporte)
        if dto.evidencia_url:
            dto.evidencia_url = self.storage_service.get_url(dto.evidencia_url) or dto.evidencia_url
        return dto

    async def listar_reportes(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        n_bus: Optional[str] = None,
    ) -> ReporteNeumaticoPaginadoDTO:
        """
        Obtiene el listado paginado de reportes de neumáticos con resolución de URLs de evidencias.
        Diseñado para la visualización y auditoría por parte de supervisión.
        """
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 20

        offset = (page - 1) * page_size
        reportes = await self.repository.list_reportes(
            db=db, limit=page_size, offset=offset, n_bus=n_bus
        )
        total = await self.repository.count(db=db, n_bus=n_bus)
        pages = math.ceil(total / page_size) if total > 0 else 0

        items_dto = []
        for r in reportes:
            dto = ReporteNeumaticoResponseDTO.model_validate(r)
            if dto.evidencia_url:
                dto.evidencia_url = self.storage_service.get_url(dto.evidencia_url) or dto.evidencia_url
            items_dto.append(dto)

        logger.info(
            "[NEUMATICO] Listado de reportes obtenido | page=%s | page_size=%s | total=%s | n_bus=%s",
            page,
            page_size,
            total,
            n_bus,
        )

        return ReporteNeumaticoPaginadoDTO(
            items=items_dto,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


formulario_neumatico_service = FormularioNeumaticoService()
