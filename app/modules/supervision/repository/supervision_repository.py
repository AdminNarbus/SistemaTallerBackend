import logging
from typing import List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.categoria_falla import CategoriaFalla

logger = logging.getLogger(__name__)


class SupervisionRepository:
    """
    Capa de consulta y agregación analítica de datos para Supervisión de Taller.
    """

    async def get_auditoria(
        self,
        db: AsyncSession,
        n_bus: Optional[str] = None,
        estado: Optional[str] = None,
        mecanico_id: Optional[int] = None,
    ) -> List[TallerSolicitud]:
        """
        Retorna la trazabilidad completa inmutable de solicitudes de taller con opción a filtrado.
        """
        logger.debug("[SUPERVISION_REPO] Consulta auditoria | n_bus=%s | estado=%s | mecanico_id=%s", n_bus, estado, mecanico_id)
        stmt = (
            select(TallerSolicitud)
            .order_by(TallerSolicitud.fecha_creacion.desc())
            .options(
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla).selectinload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
            )
        )

        if n_bus:
            stmt = stmt.where(TallerSolicitud.n_bus.ilike(f"%{n_bus.strip()}%"))
        if estado:
            stmt = stmt.where(TallerSolicitud.estado == estado.upper().strip())
        if mecanico_id:
            stmt = stmt.join(TallerSolicitudMecanico).where(TallerSolicitudMecanico.mecanico_id == mecanico_id)

        res = await db.execute(stmt)
        solicitudes = list(res.scalars().unique().all())
        logger.debug("[SUPERVISION_REPO] Solicitudes obtenidas: %s", len(solicitudes))
        return solicitudes


supervision_repository = SupervisionRepository()
