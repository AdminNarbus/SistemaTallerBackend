import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mantencion.services.mantencion_service import (
    MantencionService,
    mantencion_service,
)
from app.modules.mantencion.dtos.mantencion_dto import (
    AsignarFallasSupervisoraDTO,
    CambiarEstadoSolicitudDTO,
    SolicitudDTO,
)

from app.modules.supervision.constants import (
    DEFAULT_PAGE_SKIP,
    DEFAULT_PAGE_LIMIT,
)
from app.modules.supervision.repository.supervision_repository import (
    SupervisionRepository,
    supervision_repository,
)
from app.modules.supervision.dtos import (
    ResumenTallerDTO,
    AlertaSupervisionDTO,
    MecanicoCargaDTO,
)

logger = logging.getLogger(__name__)


class SupervisionService:
    """
    Servicio de capa de negocio para telemetría, auditoría y análisis de rendimiento del taller.
    Aplica Principio de Inversión de Dependencias (DIP) y desacoplamiento de capas.
    """

    def __init__(
        self,
        repository: Optional[SupervisionRepository] = None,
        mantencion_srv: Optional[MantencionService] = None,
    ) -> None:
        self.repo = repository or supervision_repository
        self.mantencion = mantencion_srv or mantencion_service

    async def get_auditoria_solicitudes(
        self,
        db: AsyncSession,
        n_bus: Optional[str] = None,
        estado: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
        skip: int = DEFAULT_PAGE_SKIP,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> List[SolicitudDTO]:
        """Obtiene la auditoría completa de solicitudes de taller aplicando filtros y paginación."""
        logger.info(
            "[SUPERVISION_SERVICE] Obteniendo auditoria de solicitudes | n_bus=%s | estado=%s | mecanico_nombre=%s | skip=%s | limit=%s",
            n_bus,
            estado,
            mecanico_nombre,
            skip,
            limit,
        )
        solicitudes = await self.repo.get_auditoria(
            db,
            n_bus=n_bus,
            estado=estado,
            mecanico_nombre=mecanico_nombre,
            skip=skip,
            limit=limit,
        )
        dtos: List[SolicitudDTO] = []
        for item in solicitudes:
            dto = self.mantencion.mapear_a_solicitud_dto(item)
            if dto is not None:
                dtos.append(dto)
        return dtos

    async def count_auditoria_solicitudes(
        self,
        db: AsyncSession,
        n_bus: Optional[str] = None,
        estado: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
    ) -> int:
        """Retorna el conteo total de solicitudes bajo los filtros de auditoría."""
        return await self.repo.count_auditoria(
            db, n_bus=n_bus, estado=estado, mecanico_nombre=mecanico_nombre
        )

    async def get_resumen_taller(self, db: AsyncSession) -> ResumenTallerDTO:
        """Calcula y retorna el resumen consolidado, KPIs y métricas generales del taller."""
        logger.info("[SUPERVISION_SERVICE] Calculando resumen y métricas generales del taller")
        return await self.repo.get_resumen_taller_consolidado(db)

    async def get_alertas_taller(self, db: AsyncSession) -> List[AlertaSupervisionDTO]:
        """Retorna exclusivamente las alertas operacionales activas de taller de forma directa."""
        logger.info("[SUPERVISION_SERVICE] Consultando centro de alertas operacionales activas directamente")
        return await self.repo.get_alertas_activas(db)

    async def get_mecanicos_con_carga(self, db: AsyncSession) -> List[MecanicoCargaDTO]:
        """Retorna la lista de mecánicos activos junto a su conteo de fallas asignadas y disponibilidad."""
        logger.info("[SUPERVISION_SERVICE] Consultando carga y disponibilidad de mecánicos activos")
        raw_rows = await self.repo.get_mecanicos_con_carga(db)
        return [MecanicoCargaDTO(**row) for row in raw_rows]

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
        return await self.mantencion.asignar_fallas_supervisora(
            db, solicitud_id=solicitud_id, dto=dto, supervisor_id=supervisor_id
        )

    async def cambiar_estado_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: CambiarEstadoSolicitudDTO,
        supervisor_id: int,
        supervisor_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        """
        Caso de uso de supervisión: Cambio de estado de una OT por parte de la supervisora
        con justificación en la bitácora inmutable.
        Coordina con MantencionService para la ejecución de las reglas de taller.
        """
        logger.info(
            "[SUPERVISION_SERVICE] Cambiando estado de solicitud | supervisor_id=%s | solicitud_id=%s | nuevo_estado=%s",
            supervisor_id,
            solicitud_id,
            dto.estado.value,
        )
        return await self.mantencion.cambiar_estado_solicitud(
            db,
            solicitud_id=solicitud_id,
            dto=dto,
            supervisor_id=supervisor_id,
            supervisor_nombre=supervisor_nombre,
        )


supervision_service = SupervisionService()

