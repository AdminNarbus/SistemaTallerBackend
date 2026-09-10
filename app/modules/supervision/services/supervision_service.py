import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import AsignarFallasSupervisoraDTO, SolicitudDTO
from app.modules.supervision.repository import supervision_repository
from app.modules.supervision.dtos import (
    ResumenTallerDTO,
    MetricasEstadoDTO,
    CategoriaFrecuenciaDTO,
    AlertaSupervisionDTO,
)

logger = logging.getLogger(__name__)


class SupervisionService:
    """
    Servicio de capa de negocio para telemetría, auditoría y análisis de rendimiento del taller.
    """

    async def get_auditoria_solicitudes(
        self,
        db: AsyncSession,
        n_bus: Optional[str] = None,
        estado: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[SolicitudDTO]:
        logger.info(
            "[SUPERVISION_SERVICE] Obteniendo auditoria de solicitudes | n_bus=%s | estado=%s | mecanico_nombre=%s | skip=%s | limit=%s",
            n_bus,
            estado,
            mecanico_nombre,
            skip,
            limit,
        )
        solicitudes = await supervision_repository.get_auditoria(
            db, n_bus=n_bus, estado=estado, mecanico_nombre=mecanico_nombre, skip=skip, limit=limit
        )
        return [
            mantencion_service._dict_to_solicitud_dto(s) if isinstance(s, dict) else mantencion_service._to_solicitud_dto(s)
            for s in solicitudes
        ]

    async def get_resumen_taller(self, db: AsyncSession) -> ResumenTallerDTO:
        logger.info("[SUPERVISION_SERVICE] Calculando resumen y métricas generales del taller")
        return await supervision_repository.get_resumen_taller_consolidado(db)

    async def get_alertas_taller(self, db: AsyncSession) -> List[AlertaSupervisionDTO]:
        """Retorna exclusivamente las alertas operacionales activas de taller de forma directa."""
        logger.info("[SUPERVISION_SERVICE] Consultando centro de alertas operacionales activas directamente")
        return await supervision_repository.get_alertas_activas(db)

    async def asignar_fallas_supervisora(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: AsignarFallasSupervisoraDTO,
        supervisor_id: int,
    ) -> SolicitudDTO:
        """
        Caso de uso de supervisión: Asignación directa de fallas por parte de la supervisora
        a un mecánico específico. Coordina con MantencionService para la ejecución de la regla de taller.
        """
        logger.info(
            "[SUPERVISION_SERVICE] Asignando fallas a mecánico | supervisor_id=%s | mecanico_id=%s | solicitud_id=%s",
            supervisor_id,
            dto.mecanico_id,
            solicitud_id,
        )
        return await mantencion_service.asignar_fallas_supervisora(
            db, solicitud_id=solicitud_id, dto=dto, supervisor_id=supervisor_id
        )


supervision_service = SupervisionService()
