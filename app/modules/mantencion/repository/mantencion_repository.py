import logging
from datetime import datetime
from typing import List, Optional, Set
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.mantencion.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.mantencion.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta

logger = logging.getLogger(__name__)


def _calcular_duracion_minutos(inicio: Optional[datetime], fin: Optional[datetime]) -> int:
    """
    Función utilitaria conservada para interoperabilidad.
    Calcula la duración en minutos entre dos datetimes de forma segura (naive vs aware).
    """
    if not inicio or not fin:
        return 0

    d_inicio = inicio
    d_fin = fin

    if d_inicio.tzinfo is not None and d_fin.tzinfo is None:
        try:
            d_fin = d_fin.astimezone(d_inicio.tzinfo)
        except Exception:
            pass
    elif d_inicio.tzinfo is None and d_fin.tzinfo is not None:
        try:
            d_inicio = d_inicio.astimezone(d_fin.tzinfo)
        except Exception:
            pass

    d_inicio = d_inicio.replace(tzinfo=None) if d_inicio.tzinfo else d_inicio
    d_fin = d_fin.replace(tzinfo=None) if d_fin.tzinfo else d_fin

    delta_seconds = max(0.0, (d_fin - d_inicio).total_seconds())
    return max(1, int(delta_seconds / 60))


class MantencionRepository:
    """
    Capa de acceso a datos pura (SQL/ORM) para el módulo de Taller de Mantención.
    Responsabilidad exclusiva: Ejecutar consultas SELECT y operaciones atómicas de persistencia.
    NO contiene lógica de negocio ni llamadas a db.commit().
    """

    async def get_categorias(self, db: AsyncSession) -> List[CategoriaFalla]:
        stmt = select(CategoriaFalla).where(CategoriaFalla.is_active == True)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_categoria_by_id(self, db: AsyncSession, categoria_id: int) -> Optional[CategoriaFalla]:
        return await db.get(CategoriaFalla, categoria_id)

    async def get_fallas(self, db: AsyncSession, categoria_id: Optional[int] = None) -> List[FallaTaller]:
        stmt = select(FallaTaller).where(FallaTaller.is_active == True)
        if categoria_id:
            stmt = stmt.where(FallaTaller.categoria_id == categoria_id)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_falla_by_id(self, db: AsyncSession, falla_id: int) -> Optional[FallaTaller]:
        return await db.get(FallaTaller, falla_id)

    async def find_falla_activa_by_categoria(self, db: AsyncSession, categoria_id: int) -> Optional[int]:
        stmt = (
            select(FallaTaller.id)
            .where(and_(FallaTaller.categoria_id == categoria_id, FallaTaller.is_active == True))
            .order_by(FallaTaller.id)
            .limit(1)
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def find_falla_otro(self, db: AsyncSession) -> Optional[int]:
        stmt_cat_otro = select(CategoriaFalla.id).where(CategoriaFalla.nombre == "OTRO").limit(1)
        res_cat_otro = await db.execute(stmt_cat_otro)
        otro_id = res_cat_otro.scalar_one_or_none()
        if otro_id:
            stmt_f_otro = select(FallaTaller.id).where(
                and_(FallaTaller.categoria_id == otro_id, FallaTaller.is_active == True)
            ).limit(1)
            return (await db.execute(stmt_f_otro)).scalar_one_or_none()
        return None

    async def get_bus_id_by_n_bus(self, db: AsyncSession, n_bus: str) -> Optional[int]:
        clean_nb = str(n_bus).strip()
        stmt = select(Bus.id).where(Bus.n_bus == clean_nb)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_bus_by_id(self, db: AsyncSession, bus_id: int) -> Optional[Bus]:
        return await db.get(Bus, bus_id)

    async def get_usuario_by_id(self, db: AsyncSession, usuario_id: int) -> Optional[Usuario]:
        return await db.get(Usuario, usuario_id)

    async def get_solicitud_by_id(self, db: AsyncSession, solicitud_id: int) -> Optional[TallerSolicitud]:
        logger.debug("[MANTENCION-REPO] Query get_solicitud_by_id | id=%s", solicitud_id)
        db.expire_all()
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.id == solicitud_id)
            .options(
                selectinload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla).selectinload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.asignado_por),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.asignado_por),
                selectinload(TallerSolicitud.pauta_respuestas).selectinload(TallerSolicitudPauta.item),
                selectinload(TallerSolicitud.pauta_respuestas).selectinload(TallerSolicitudPauta.mecanico),
            )
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_pendientes(self, db: AsyncSession) -> List[TallerSolicitud]:
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.estado.in_(["REPORTADO", "PENDIENTE", "PENDIENTE_REASIGNACION"]))
            .order_by(TallerSolicitud.fecha_creacion.asc())
            .options(
                selectinload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla).selectinload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.mecanico),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def list_mis_trabajos(self, db: AsyncSession, mecanico_id: int) -> List[TallerSolicitud]:
        stmt = (
            select(TallerSolicitud)
            .distinct()
            .outerjoin(
                TallerSolicitudMecanico,
                and_(
                    TallerSolicitudMecanico.solicitud_id == TallerSolicitud.id,
                    TallerSolicitudMecanico.mecanico_id == mecanico_id,
                    TallerSolicitudMecanico.is_activo == True,
                ),
            )
            .outerjoin(
                TallerAsignacionFalla,
                and_(
                    TallerAsignacionFalla.solicitud_id == TallerSolicitud.id,
                    TallerAsignacionFalla.mecanico_id == mecanico_id,
                    TallerAsignacionFalla.is_activo == True,
                ),
            )
            .where(
                and_(
                    or_(TallerSolicitudMecanico.id.isnot(None), TallerAsignacionFalla.id.isnot(None)),
                    TallerSolicitud.estado == "EN_REPARACION",
                )
            )
            .order_by(TallerSolicitud.fecha_creacion.desc())
            .options(
                selectinload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla).selectinload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.mecanico),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def list_auditoria(self, db: AsyncSession) -> List[TallerSolicitud]:
        stmt = (
            select(TallerSolicitud)
            .order_by(TallerSolicitud.fecha_creacion.desc())
            .options(
                selectinload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla).selectinload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.mecanico),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_pauta_items(self, db: AsyncSession) -> List[PautaTallerItem]:
        stmt = (
            select(PautaTallerItem)
            .where(PautaTallerItem.is_active == True)
            .order_by(PautaTallerItem.orden.asc(), PautaTallerItem.id.asc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_pauta_items_by_ids(self, db: AsyncSession, item_ids: List[int]) -> Set[int]:
        stmt = select(PautaTallerItem.id).where(PautaTallerItem.id.in_(item_ids))
        res = await db.execute(stmt)
        return set(res.scalars().all())

    async def get_pauta_respuestas_by_solicitud(
        self, db: AsyncSession, solicitud_id: int
    ) -> List[TallerSolicitudPauta]:
        stmt = (
            select(TallerSolicitudPauta)
            .where(TallerSolicitudPauta.solicitud_id == solicitud_id)
            .options(
                selectinload(TallerSolicitudPauta.item),
                selectinload(TallerSolicitudPauta.mecanico),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_asignaciones_activas(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalles_ids: Optional[List[int]] = None,
        mecanicos_ids: Optional[List[int]] = None,
    ) -> List[TallerAsignacionFalla]:
        stmt = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.is_activo == True,
            )
        )
        if detalles_ids:
            stmt = stmt.where(TallerAsignacionFalla.detalle_id.in_(detalles_ids))
        if mecanicos_ids:
            stmt = stmt.where(TallerAsignacionFalla.mecanico_id.in_(mecanicos_ids))
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_presencias_activas(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: Optional[int] = None
    ) -> List[TallerSolicitudMecanico]:
        stmt = select(TallerSolicitudMecanico).where(
            and_(
                TallerSolicitudMecanico.solicitud_id == solicitud_id,
                TallerSolicitudMecanico.is_activo == True,
            )
        )
        if mecanico_id:
            stmt = stmt.where(TallerSolicitudMecanico.mecanico_id == mecanico_id)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_presencia_activa_individual(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: int
    ) -> Optional[TallerSolicitudMecanico]:
        stmt = select(TallerSolicitudMecanico).where(
            and_(
                TallerSolicitudMecanico.solicitud_id == solicitud_id,
                TallerSolicitudMecanico.mecanico_id == mecanico_id,
                TallerSolicitudMecanico.is_activo == True,
            )
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_asignaciones_activas_restantes(
        self, db: AsyncSession, solicitud_id: int, mecanicos_ids: Set[int], excluir_ids: Set[int]
    ) -> Set[int]:
        stmt = select(TallerAsignacionFalla.mecanico_id).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.mecanico_id.in_(mecanicos_ids),
                TallerAsignacionFalla.is_activo == True,
                TallerAsignacionFalla.id.not_in(excluir_ids),
            )
        )
        res = await db.execute(stmt)
        return set(res.scalars().all())

    async def get_otras_asignaciones_activas(
        self, db: AsyncSession, solicitud_id: int, excluir_ids: Set[int]
    ) -> bool:
        stmt = select(TallerAsignacionFalla.id).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.is_activo == True,
                TallerAsignacionFalla.id.not_in(excluir_ids),
            )
        )
        res = await db.execute(stmt)
        return bool(res.scalars().all())

    # --- Métodos Atómicos de Escritura (Persistencia pura sin commit) ---

    def add_solicitud(self, db: AsyncSession, solicitud: TallerSolicitud) -> None:
        db.add(solicitud)

    def add_detalle(self, db: AsyncSession, detalle: TallerSolicitudDetalle) -> None:
        db.add(detalle)

    def add_falla(self, db: AsyncSession, falla: FallaTaller) -> None:
        db.add(falla)

    def add_mecanico(self, db: AsyncSession, mecanico_entry: TallerSolicitudMecanico) -> None:
        db.add(mecanico_entry)

    def add_asignacion_falla(self, db: AsyncSession, asignacion_entry: TallerAsignacionFalla) -> None:
        db.add(asignacion_entry)

    def add_comentario(self, db: AsyncSession, comentario_entry: TallerSolicitudComentario) -> None:
        db.add(comentario_entry)

    def add_pauta_respuesta(self, db: AsyncSession, pauta_entry: TallerSolicitudPauta) -> None:
        db.add(pauta_entry)

    async def desactivar_mecanicos_activos(
        self, db: AsyncSession, solicitud_id: int, fecha_desasignacion: datetime
    ) -> List[TallerSolicitudMecanico]:
        """
        Método atómico de persistencia: Busca y desactiva todos los registros de presencia
        activa de mecánicos para la solicitud indicada.
        """
        stmt = select(TallerSolicitudMecanico).where(
            and_(
                TallerSolicitudMecanico.solicitud_id == solicitud_id,
                TallerSolicitudMecanico.is_activo == True,
            )
        )
        res = await db.execute(stmt)
        mecs = list(res.scalars().all())
        for mec in mecs:
            mec.is_activo = False
            mec.fecha_desasignacion = fecha_desasignacion
        await db.flush()
        return mecs

    async def desactivar_mecanicos_por_ids(
        self, db: AsyncSession, solicitud_id: int, mecanicos_ids: Set[int], fecha_desasignacion: datetime
    ) -> List[TallerSolicitudMecanico]:
        """
        Método atómico de persistencia: Desactiva mecánicos activos específicos por su mecanico_id.
        """
        if not mecanicos_ids:
            return []
        stmt = select(TallerSolicitudMecanico).where(
            and_(
                TallerSolicitudMecanico.solicitud_id == solicitud_id,
                TallerSolicitudMecanico.mecanico_id.in_(mecanicos_ids),
                TallerSolicitudMecanico.is_activo == True,
            )
        )
        res = await db.execute(stmt)
        mecs = list(res.scalars().all())
        for mec in mecs:
            mec.is_activo = False
            mec.fecha_desasignacion = fecha_desasignacion
        await db.flush()
        return mecs

    async def flush(self, db: AsyncSession) -> None:
        await db.flush()


mantencion_repository = MantencionRepository()
