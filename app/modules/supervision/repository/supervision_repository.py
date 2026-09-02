import logging
from typing import List, Optional
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, aliased

from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.mantencion.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.mantencion.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.buses.models.bus import Bus
from app.modules.auth.models.usuario import Usuario

logger = logging.getLogger(__name__)


class SupervisionRepository:
    """
    Capa de consulta y agregación analítica de datos para Supervisión de Taller.
    """

    async def get_total_buses_en_taller(self, db: AsyncSession) -> int:
        """Retorna el conteo de buses operativos marcados físicamente en taller."""
        stmt = select(func.count(Bus.id)).where(Bus.en_taller == True, Bus.is_active == True)
        res = await db.execute(stmt)
        return res.scalar() or 0

    async def get_auditoria(
        self,
        db: AsyncSession,
        n_bus: Optional[str] = None,
        estado: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
    ) -> List[TallerSolicitud]:
        """
        Retorna la trazabilidad completa inmutable de solicitudes de taller con opción a filtrado por bus, estado y nombre/username del mecánico.
        """
        logger.debug("[SUPERVISION_REPO] Consulta auditoria | n_bus=%s | estado=%s | mecanico_nombre=%s", n_bus, estado, mecanico_nombre)
        stmt = (
            select(TallerSolicitud)
            .order_by(TallerSolicitud.fecha_creacion.desc())
            .options(
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla).selectinload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.asignado_por),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.pauta_respuestas).selectinload(TallerSolicitudPauta.item),
                selectinload(TallerSolicitud.pauta_respuestas).selectinload(TallerSolicitudPauta.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
            )
        )


        if n_bus and n_bus.strip():
            stmt = stmt.where(TallerSolicitud.n_bus.ilike(f"%{n_bus.strip()}%"))
        if estado and estado.strip():
            stmt = stmt.where(TallerSolicitud.estado == estado.upper().strip())
        if mecanico_nombre and mecanico_nombre.strip():
            pattern = f"%{mecanico_nombre.strip()}%"
            u_mec = aliased(Usuario)
            u_res = aliased(Usuario)
            stmt = (
                stmt.outerjoin(TallerSolicitud.mecanicos)
                .outerjoin(u_mec, TallerSolicitudMecanico.mecanico)
                .outerjoin(TallerSolicitud.detalles)
                .outerjoin(u_res, TallerSolicitudDetalle.mecanico_resolvio)
                .where(
                    or_(
                        u_mec.nombre.ilike(pattern),
                        u_mec.apellido.ilike(pattern),
                        u_mec.username.ilike(pattern),
                        func.concat(u_mec.nombre, ' ', u_mec.apellido).ilike(pattern),
                        u_res.nombre.ilike(pattern),
                        u_res.apellido.ilike(pattern),
                        u_res.username.ilike(pattern),
                        func.concat(u_res.nombre, ' ', u_res.apellido).ilike(pattern),
                    )
                )
            )

        res = await db.execute(stmt)
        solicitudes = list(res.scalars().unique().all())
        logger.debug("[SUPERVISION_REPO] Solicitudes obtenidas: %s", len(solicitudes))
        return solicitudes


supervision_repository = SupervisionRepository()
