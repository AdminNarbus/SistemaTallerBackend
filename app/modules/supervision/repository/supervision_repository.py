import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload, aliased

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
from app.modules.supervision.dtos.supervision_dto import AlertaSupervisionDTO

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

    async def get_conteos_por_estado(self, db: AsyncSession) -> Dict[str, int]:
        """Agregación SQL nativa para contar órdenes de taller agrupadas por estado."""
        stmt = select(TallerSolicitud.estado, func.count(TallerSolicitud.id)).group_by(TallerSolicitud.estado)
        res = await db.execute(stmt)
        return {row[0]: row[1] for row in res.all()}

    async def get_conteos_fallas(self, db: AsyncSession) -> Tuple[int, int]:
        """Agregación SQL nativa: (total_fallas, total_resueltas)."""
        stmt = select(
            func.count(TallerSolicitudDetalle.id),
            func.count(TallerSolicitudDetalle.id).filter(TallerSolicitudDetalle.resuelto == True),
        )
        res = await db.execute(stmt)
        row = res.one_or_none()
        if not row:
            return 0, 0
        return row[0] or 0, row[1] or 0

    async def get_fallas_por_categoria(self, db: AsyncSession) -> List[Tuple[Optional[int], Optional[str], int]]:
        """Agregación SQL nativa: agrupa conteo de fallas registradas por categoría."""
        stmt = (
            select(
                CategoriaFalla.id,
                CategoriaFalla.nombre,
                func.count(TallerSolicitudDetalle.id),
            )
            .select_from(TallerSolicitudDetalle)
            .outerjoin(FallaTaller, TallerSolicitudDetalle.falla_id == FallaTaller.id)
            .outerjoin(CategoriaFalla, FallaTaller.categoria_id == CategoriaFalla.id)
            .group_by(CategoriaFalla.id, CategoriaFalla.nombre)
        )
        res = await db.execute(stmt)
        return list(res.all())

    async def get_alertas_activas(self, db: AsyncSession) -> List[AlertaSupervisionDTO]:
        """
        Consulta analítica directa de alertas operacionales activas.
        En lugar de cargar todas las entidades en memoria, ejecuta consultas dirigidas
        únicamente a las condiciones de anomalía en órdenes no finalizadas.
        """
        alertas: List[AlertaSupervisionDTO] = []

        # 1. Alertas por falta de repuestos
        stmt_rep = (
            select(
                TallerSolicitud.id,
                TallerSolicitud.n_bus,
                TallerSolicitudDetalle.id,
                TallerSolicitudDetalle.comentario_repuesto,
            )
            .join(TallerSolicitud, TallerSolicitudDetalle.solicitud_id == TallerSolicitud.id)
            .where(
                TallerSolicitudDetalle.falta_repuesto == True,
                TallerSolicitud.estado != "FINALIZADO",
            )
            .order_by(TallerSolicitud.id.desc())
        )
        res_rep = await db.execute(stmt_rep)
        for sol_id, n_bus, det_id, com_rep in res_rep.all():
            msg = f"Falla #{det_id} en Bus {n_bus} detenida por falta de repuestos"
            if com_rep:
                msg += f": {com_rep}"
            alertas.append(
                AlertaSupervisionDTO(
                    tipo="REPUESTO_FALTANTE",
                    severidad="ALTA",
                    solicitud_id=sol_id,
                    n_bus=n_bus or "S/N",
                    detalle_id=det_id,
                    mensaje=msg,
                )
            )

        # 2. Alertas por defectos en pauta preventiva
        stmt_pauta = (
            select(
                TallerSolicitud.id,
                TallerSolicitud.n_bus,
                TallerSolicitudPauta.item_id,
                PautaTallerItem.item,
            )
            .join(TallerSolicitud, TallerSolicitudPauta.solicitud_id == TallerSolicitud.id)
            .outerjoin(PautaTallerItem, TallerSolicitudPauta.item_id == PautaTallerItem.id)
            .where(
                TallerSolicitudPauta.estado == "DEFECTO",
                TallerSolicitud.estado != "FINALIZADO",
            )
            .order_by(TallerSolicitud.id.desc())
        )
        res_pauta = await db.execute(stmt_pauta)
        for sol_id, n_bus, item_id, item_nombre in res_pauta.all():
            item_txt = item_nombre if item_nombre else f"Ítem #{item_id}"
            alertas.append(
                AlertaSupervisionDTO(
                    tipo="DEFECTO_PAUTA",
                    severidad="MEDIA",
                    solicitud_id=sol_id,
                    n_bus=n_bus or "S/N",
                    mensaje=f"Ítem de pauta preventiva con defecto en Bus {n_bus}: {item_txt}",
                )
            )

        # 3. Alertas por buses en reparación sin mecánicos ni asignaciones activas
        sub_mec_activo = select(1).where(
            TallerSolicitudMecanico.solicitud_id == TallerSolicitud.id,
            TallerSolicitudMecanico.is_activo == True,
        )
        sub_asig_activa = select(1).where(
            TallerAsignacionFalla.solicitud_id == TallerSolicitud.id,
            TallerAsignacionFalla.is_activo == True,
        )
        stmt_sin_mec = (
            select(TallerSolicitud.id, TallerSolicitud.n_bus)
            .where(
                TallerSolicitud.estado == "EN_REPARACION",
                ~sub_mec_activo.exists(),
                ~sub_asig_activa.exists(),
            )
            .order_by(TallerSolicitud.id.desc())
        )
        res_sin_mec = await db.execute(stmt_sin_mec)
        for sol_id, n_bus in res_sin_mec.all():
            alertas.append(
                AlertaSupervisionDTO(
                    tipo="BUS_SIN_MECANICOS",
                    severidad="MEDIA",
                    solicitud_id=sol_id,
                    n_bus=n_bus or "S/N",
                    mensaje=f"Bus {n_bus} figura EN_REPARACION pero no tiene mecánicos activos asignados",
                )
            )

        return alertas

    async def get_buses_activos_taller(self, db: AsyncSession) -> List[str]:
        """Retorna lista única de números de bus actualmente en órdenes abiertas."""
        stmt = (
            select(TallerSolicitud.n_bus)
            .where(TallerSolicitud.estado != "FINALIZADO", TallerSolicitud.n_bus.isnot(None))
            .distinct()
        )
        res = await db.execute(stmt)
        return [r[0] for r in res.all() if r[0]]

    async def get_auditoria(
        self,
        db: AsyncSession,
        n_bus: Optional[str] = None,
        estado: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[TallerSolicitud]:
        """
        Retorna la trazabilidad completa inmutable de solicitudes de taller con opción a filtrado
        por bus, estado y nombre/username del mecánico, con paginación integrada y joins optimizados.
        """
        logger.debug(
            "[SUPERVISION_REPO] Consulta auditoria | n_bus=%s | estado=%s | mecanico_nombre=%s | skip=%s | limit=%s",
            n_bus,
            estado,
            mecanico_nombre,
            skip,
            limit,
        )
        stmt = (
            select(TallerSolicitud)
            .order_by(TallerSolicitud.fecha_creacion.desc())
            .options(
                joinedload(TallerSolicitud.creador),
                joinedload(TallerSolicitud.mecanico_cierre),
                joinedload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.falla).joinedload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).joinedload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).joinedload(TallerAsignacionFalla.asignado_por),
                selectinload(TallerSolicitud.mecanicos).joinedload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.pauta_respuestas).joinedload(TallerSolicitudPauta.item),
                selectinload(TallerSolicitud.pauta_respuestas).joinedload(TallerSolicitudPauta.mecanico),
                selectinload(TallerSolicitud.comentarios).joinedload(TallerSolicitudComentario.usuario),
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
            
            # Subconsultas EXISTS para evitar producto cartesiano y duplicación de filas en la consulta raíz
            sub_mec = (
                select(1)
                .select_from(TallerSolicitudMecanico)
                .join(u_mec, TallerSolicitudMecanico.mecanico_id == u_mec.id)
                .where(
                    TallerSolicitudMecanico.solicitud_id == TallerSolicitud.id,
                    or_(
                        u_mec.nombre.ilike(pattern),
                        u_mec.apellido.ilike(pattern),
                        u_mec.username.ilike(pattern),
                        func.concat(u_mec.nombre, ' ', u_mec.apellido).ilike(pattern),
                    ),
                )
            )
            sub_res = (
                select(1)
                .select_from(TallerSolicitudDetalle)
                .join(u_res, TallerSolicitudDetalle.mecanico_resolvio_id == u_res.id)
                .where(
                    TallerSolicitudDetalle.solicitud_id == TallerSolicitud.id,
                    or_(
                        u_res.nombre.ilike(pattern),
                        u_res.apellido.ilike(pattern),
                        u_res.username.ilike(pattern),
                        func.concat(u_res.nombre, ' ', u_res.apellido).ilike(pattern),
                    ),
                )
            )
            stmt = stmt.where(or_(sub_mec.exists(), sub_res.exists()))

        if skip:
            stmt = stmt.offset(skip)
        if limit:
            stmt = stmt.limit(limit)

        res = await db.execute(stmt)
        solicitudes = list(res.scalars().unique().all())
        logger.debug("[SUPERVISION_REPO] Solicitudes obtenidas: %s", len(solicitudes))
        return solicitudes


supervision_repository = SupervisionRepository()
