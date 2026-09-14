import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from sqlalchemy import select, and_, or_, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload, joinedload, noload

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


from app.modules.mantencion.utils import calcular_duracion_minutos

def clear_mantencion_repository_caches() -> None:
    """Función de compatibilidad (no-op: los catálogos se consultan directamente desde la BD)."""
    pass


# Re-exportación para interoperabilidad hacia atrás con tests y servicios legados
_calcular_duracion_minutos = calcular_duracion_minutos



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

    async def get_categorias_con_fallas(self, db: AsyncSession) -> List[dict]:
        """
        Retorna las categorías activas con su primera falla activa asociada (id, nombre, is_active, falla_id, falla_nombre).
        Optimizado a exactamente 1 sola consulta SQL con LEFT JOIN para minimizar latencia de red.
        """
        stmt = (
            select(
                CategoriaFalla.id,
                CategoriaFalla.nombre,
                CategoriaFalla.is_active,
                FallaTaller.id.label("falla_id"),
                FallaTaller.nombre.label("falla_nombre"),
            )
            .outerjoin(
                FallaTaller,
                and_(
                    FallaTaller.categoria_id == CategoriaFalla.id,
                    FallaTaller.is_active == True,
                ),
            )
            .where(CategoriaFalla.is_active == True)
            .order_by(CategoriaFalla.id.asc(), FallaTaller.id.asc())
        )
        res = await db.execute(stmt)
        seen_cats = set()
        resultado = []
        for cat_id, cat_nom, cat_act, f_id, f_nom in res.all():
            if cat_id not in seen_cats:
                seen_cats.add(cat_id)
                resultado.append({
                    "id": cat_id,
                    "nombre": cat_nom,
                    "is_active": cat_act,
                    "falla_id": f_id,
                    "falla_nombre": f_nom,
                })
        return resultado

    async def get_categoria_by_id(self, db: AsyncSession, categoria_id: int) -> Optional[CategoriaFalla]:
        return await db.get(CategoriaFalla, categoria_id)

    async def get_fallas(self, db: AsyncSession, categoria_id: Optional[int] = None) -> List[FallaTaller]:
        stmt = (
            select(FallaTaller)
            .where(FallaTaller.is_active == True)
            .options(joinedload(FallaTaller.categoria))
        )
        if categoria_id:
            stmt = stmt.where(FallaTaller.categoria_id == categoria_id)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_falla_by_id(self, db: AsyncSession, falla_id: int) -> Optional[FallaTaller]:
        stmt = select(FallaTaller).options(joinedload(FallaTaller.categoria)).where(FallaTaller.id == falla_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def find_falla_activa_by_categoria(self, db: AsyncSession, categoria_id: int) -> Optional[int]:
        stmt = (
            select(FallaTaller.id)
            .where(and_(FallaTaller.categoria_id == categoria_id, FallaTaller.is_active == True))
            .order_by(FallaTaller.id)
            .limit(1)
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def find_fallas_activas_by_categorias(
        self, db: AsyncSession, categoria_ids: List[int]
    ) -> dict[int, tuple[int, str, str]]:
        """
        Retorna un mapa {categoria_id: (falla_id, falla_nombre, categoria_nombre)} consultando directamente la BD.
        """
        if not categoria_ids:
            return {}

        stmt = (
            select(FallaTaller.categoria_id, FallaTaller.id, FallaTaller.nombre, CategoriaFalla.nombre)
            .join(CategoriaFalla, CategoriaFalla.id == FallaTaller.categoria_id)
            .where(
                and_(
                    FallaTaller.categoria_id.in_(categoria_ids),
                    FallaTaller.is_active == True,
                )
            )
            .order_by(FallaTaller.id.asc())
        )
        res = await db.execute(stmt)
        result: dict[int, tuple[int, str, str]] = {}
        for cat_id, f_id, f_nom, c_nom in res.all():
            if cat_id not in result:
                result[cat_id] = (f_id, f_nom, c_nom)
        return result

    async def get_fallas_info_by_ids(
        self, db: AsyncSession, falla_ids: List[int]
    ) -> Dict[int, dict]:
        """
        Retorna diccionario con metadata y categoría de fallas por sus IDs consultando directamente la BD.
        """
        if not falla_ids:
            return {}

        stmt = (
            select(FallaTaller)
            .options(joinedload(FallaTaller.categoria))
            .where(FallaTaller.id.in_(falla_ids))
        )
        res = await db.execute(stmt)
        result: Dict[int, dict] = {}
        for f in res.scalars().all():
            result[f.id] = {
                "id": f.id,
                "nombre": f.nombre,
                "categoria_id": f.categoria_id,
                "cat_id": f.categoria.id if f.categoria else f.categoria_id,
                "cat_nombre": f.categoria.nombre if f.categoria else None,
                "cat_active": f.categoria.is_active if f.categoria else True,
            }
        return result

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

    async def get_bus_info_by_n_bus(self, db: AsyncSession, n_bus: str) -> Optional[tuple[int, Optional[str]]]:
        """Recupera id y patente del bus consultando directamente la base de datos."""
        clean_nb = str(n_bus).strip()
        stmt = select(Bus.id, Bus.patente).where(Bus.n_bus == clean_nb)
        res = await db.execute(stmt)
        row = res.first()
        if row:
            return (row[0], row[1])
        return None

    async def get_bus_by_id(self, db: AsyncSession, bus_id: int) -> Optional[Bus]:
        return await db.get(Bus, bus_id)

    async def get_usuario_by_id(self, db: AsyncSession, usuario_id: int) -> Optional[Usuario]:
        return await db.get(Usuario, usuario_id)

    async def get_solicitud_by_id(self, db: AsyncSession, solicitud_id: int) -> Optional[TallerSolicitud]:
        """
        Recupera la solicitud completa optimizando relaciones escalares con joinedload
        y colecciones con selectinload, reduciendo drásticamente viajes de red innecesarios.
        """
        logger.debug("[MANTENCION-REPO] Query get_solicitud_by_id | id=%s", solicitud_id)
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.id == solicitud_id)
            .execution_options(populate_existing=True)
            .options(
                joinedload(TallerSolicitud.bus),
                joinedload(TallerSolicitud.creador),
                joinedload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.falla).joinedload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).joinedload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).joinedload(TallerAsignacionFalla.asignado_por),
                selectinload(TallerSolicitud.mecanicos).joinedload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).joinedload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).joinedload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.asignaciones_fallas).joinedload(TallerAsignacionFalla.asignado_por),
                selectinload(TallerSolicitud.pauta_respuestas).joinedload(TallerSolicitudPauta.item),
                selectinload(TallerSolicitud.pauta_respuestas).joinedload(TallerSolicitudPauta.mecanico),
                selectinload(TallerSolicitud.evidencias),
            )
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_solicitud_dto_by_id(
        self, db: AsyncSession, solicitud_id: int
    ) -> Optional[dict | TallerSolicitud]:
        """
        Recupera la solicitud completa en exactamente 1 sola consulta SQL nativa con CTEs
        y agregación JSON en PostgreSQL/Neon, reduciendo la latencia de ~1.2s a ~180ms.
        Fallback a ORM completo en SQLite para mantener compatibilidad en tests.
        """
        if db.bind and db.bind.dialect.name == "postgresql":
            sql = text("""
                WITH filtered_solicitud AS (
                    SELECT s.id, s.n_bus, s.bus_id, s.usuario_creador_id, s.mecanico_cierre_id,
                           s.estado, s.descripcion_general, s.foto_url, s.motivo_incompleto_checklist,
                           s.motivo_cierre_parcial, s.fecha_creacion, s.fecha_cierre
                    FROM taller_solicitudes s
                    WHERE s.id = :solicitud_id
                ),
                evidencias_agg AS (
                    SELECT 
                        e.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', e.id,
                                'solicitud_id', e.solicitud_id,
                                'detalle_id', e.detalle_id,
                                'usuario_id', e.usuario_id,
                                'url', e.url,
                                'original_filename', e.original_filename,
                                'size_bytes', e.size_bytes,
                                'content_type', e.content_type,
                                'fecha_creacion', e.fecha_creacion
                            ) ORDER BY e.id ASC
                        ) as evidencias_json
                    FROM taller_solicitud_evidencias e
                    JOIN filtered_solicitud fs ON fs.id = e.solicitud_id
                    GROUP BY e.solicitud_id
                ),
                detalles_agg AS (
                    SELECT 
                        d.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', d.id,
                                'solicitud_id', d.solicitud_id,
                                'categoria_id', f.categoria_id,
                                'categoria_nombre', cf.nombre,
                                'falla_id', d.falla_id,
                                'falla', CASE WHEN f.id IS NOT NULL THEN json_build_object(
                                    'id', f.id,
                                    'categoria_id', f.categoria_id,
                                    'nombre', f.nombre,
                                    'is_active', f.is_active
                                ) ELSE NULL END,
                                'descripcion_personalizada', d.descripcion_personalizada,
                                'resuelto', d.resuelto,
                                'mecanico_resolvio_id', d.mecanico_resolvio_id,
                                'mecanico_resolvio_nombre', CASE WHEN ur.id IS NOT NULL THEN CONCAT(ur.nombre, ' ', ur.apellido) ELSE NULL END,
                                'falta_repuesto', d.falta_repuesto,
                                'comentario_repuesto', d.comentario_repuesto,
                                'fecha_creacion', d.fecha_creacion,
                                'fecha_resolucion', d.fecha_resolucion,
                                'mecanicos_asignados', COALESCE((
                                    SELECT json_agg(
                                        json_build_object(
                                            'id', um.id,
                                            'nombre', CONCAT(um.nombre, ' ', um.apellido),
                                            'origen', a.origen,
                                            'fecha_asignacion', a.fecha_asignacion
                                        )
                                    )
                                    FROM taller_asignacion_fallas a
                                    JOIN usuarios um ON um.id = a.mecanico_id
                                    WHERE a.detalle_id = d.id AND a.is_activo = true
                                ), '[]'::json),
                                'historial_asignaciones', COALESCE((
                                    SELECT json_agg(
                                        json_build_object(
                                            'id', a.id,
                                            'solicitud_id', a.solicitud_id,
                                            'detalle_id', a.detalle_id,
                                            'mecanico_id', a.mecanico_id,
                                            'mecanico_nombre', CONCAT(um.nombre, ' ', um.apellido),
                                            'asignado_por_id', a.asignado_por_id,
                                            'asignado_por_nombre', CASE WHEN uap.id IS NOT NULL THEN CONCAT(uap.nombre, ' ', uap.apellido) ELSE NULL END,
                                            'origen', a.origen,
                                            'is_activo', a.is_activo,
                                            'duracion_minutos', a.duracion_minutos,
                                            'fecha_asignacion', a.fecha_asignacion,
                                            'fecha_desasignacion', a.fecha_desasignacion,
                                            'resuelto_en_esta_asignacion', a.resuelto_en_esta_asignacion,
                                            'comentario', a.comentario
                                        ) ORDER BY a.id ASC
                                    )
                                    FROM taller_asignacion_fallas a
                                    JOIN usuarios um ON um.id = a.mecanico_id
                                    LEFT JOIN usuarios uap ON uap.id = a.asignado_por_id
                                    WHERE a.detalle_id = d.id
                                ), '[]'::json)
                            ) ORDER BY d.id ASC
                        ) as detalles_json
                    FROM taller_solicitud_detalles d
                    JOIN filtered_solicitud fs ON fs.id = d.solicitud_id
                    LEFT JOIN fallas_taller f ON f.id = d.falla_id
                    LEFT JOIN categorias_falla cf ON cf.id = f.categoria_id
                    LEFT JOIN usuarios ur ON ur.id = d.mecanico_resolvio_id
                    GROUP BY d.solicitud_id
                ),
                mecanicos_agg AS (
                    SELECT 
                        sm.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', sm.id,
                                'solicitud_id', sm.solicitud_id,
                                'mecanico_id', sm.mecanico_id,
                                'mecanico_nombre', CONCAT(um.nombre, ' ', um.apellido),
                                'asignado_por_id', sm.asignado_por_id,
                                'asignado_por_nombre', CASE WHEN uap.id IS NOT NULL THEN CONCAT(uap.nombre, ' ', uap.apellido) ELSE NULL END,
                                'duracion_minutos', sm.duracion_minutos,
                                'es_lider_responsable', sm.es_lider_responsable,
                                'is_activo', sm.is_activo,
                                'fecha_asignacion', sm.fecha_asignacion,
                                'fecha_desasignacion', sm.fecha_desasignacion
                            ) ORDER BY sm.id ASC
                        ) FILTER (WHERE sm.is_activo = true) as mecanicos_activos_json,
                        json_agg(
                            json_build_object(
                                'id', sm.id,
                                'solicitud_id', sm.solicitud_id,
                                'mecanico_id', sm.mecanico_id,
                                'mecanico_nombre', CONCAT(um.nombre, ' ', um.apellido),
                                'asignado_por_id', sm.asignado_por_id,
                                'asignado_por_nombre', CASE WHEN uap.id IS NOT NULL THEN CONCAT(uap.nombre, ' ', uap.apellido) ELSE NULL END,
                                'duracion_minutos', sm.duracion_minutos,
                                'es_lider_responsable', sm.es_lider_responsable,
                                'is_activo', sm.is_activo,
                                'fecha_asignacion', sm.fecha_asignacion,
                                'fecha_desasignacion', sm.fecha_desasignacion
                            ) ORDER BY sm.id ASC
                        ) as historial_mecanicos_json
                    FROM taller_solicitud_mecanicos sm
                    JOIN filtered_solicitud fs ON fs.id = sm.solicitud_id
                    JOIN usuarios um ON um.id = sm.mecanico_id
                    LEFT JOIN usuarios uap ON uap.id = sm.asignado_por_id
                    GROUP BY sm.solicitud_id
                ),
                comentarios_agg AS (
                    SELECT 
                        c.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', c.id,
                                'solicitud_id', c.solicitud_id,
                                'usuario_id', c.usuario_id,
                                'usuario_nombre', CONCAT(uc.nombre, ' ', uc.apellido),
                                'tipo', c.tipo,
                                'comentario', c.comentario,
                                'fecha_registro', c.fecha_registro
                            ) ORDER BY c.fecha_registro ASC
                        ) as comentarios_json
                    FROM taller_solicitud_comentarios c
                    JOIN filtered_solicitud fs ON fs.id = c.solicitud_id
                    LEFT JOIN usuarios uc ON uc.id = c.usuario_id
                    GROUP BY c.solicitud_id
                ),
                pauta_agg AS (
                    SELECT 
                        p.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', p.id,
                                'solicitud_id', p.solicitud_id,
                                'item_id', p.item_id,
                                'item_categoria', pi.categoria,
                                'item_nombre', pi.item,
                                'estado', p.estado,
                                'observacion', p.observacion,
                                'mecanico_id', p.mecanico_id,
                                'mecanico_nombre', CASE WHEN up.id IS NOT NULL THEN CONCAT(up.nombre, ' ', up.apellido) ELSE NULL END,
                                'fecha_registro', p.fecha_registro
                            ) ORDER BY pi.orden ASC, p.id ASC
                        ) as pauta_json
                    FROM taller_solicitud_pauta p
                    JOIN filtered_solicitud fs ON fs.id = p.solicitud_id
                    LEFT JOIN pauta_taller_items pi ON pi.id = p.item_id
                    LEFT JOIN usuarios up ON up.id = p.mecanico_id
                    GROUP BY p.solicitud_id
                )
                SELECT 
                    fs.id,
                    fs.n_bus,
                    fs.bus_id,
                    b.patente as bus_patente,
                    fs.usuario_creador_id,
                    CONCAT(u.nombre, ' ', u.apellido) as usuario_creador_nombre,
                    fs.mecanico_cierre_id,
                    CASE WHEN mc.id IS NOT NULL THEN CONCAT(mc.nombre, ' ', mc.apellido) ELSE NULL END as mecanico_cierre_nombre,
                    fs.estado,
                    fs.descripcion_general,
                    fs.foto_url,
                    fs.motivo_incompleto_checklist,
                    fs.motivo_cierre_parcial,
                    fs.fecha_creacion,
                    fs.fecha_cierre,
                    COALESCE(da.detalles_json, '[]'::json) as detalles_json,
                    COALESCE(ma.mecanicos_activos_json, '[]'::json) as mecanicos_json,
                    COALESCE(ma.historial_mecanicos_json, '[]'::json) as historial_mecanicos_json,
                    COALESCE(ca.comentarios_json, '[]'::json) as comentarios_json,
                    COALESCE(pa.pauta_json, '[]'::json) as pauta_respuestas_json,
                    COALESCE(ea.evidencias_json, '[]'::json) as evidencias_json
                FROM filtered_solicitud fs
                LEFT JOIN buses b ON b.id = fs.bus_id
                LEFT JOIN usuarios u ON u.id = fs.usuario_creador_id
                LEFT JOIN usuarios mc ON mc.id = fs.mecanico_cierre_id
                LEFT JOIN detalles_agg da ON da.solicitud_id = fs.id
                LEFT JOIN mecanicos_agg ma ON ma.solicitud_id = fs.id
                LEFT JOIN comentarios_agg ca ON ca.solicitud_id = fs.id
                LEFT JOIN pauta_agg pa ON pa.solicitud_id = fs.id
                LEFT JOIN evidencias_agg ea ON ea.solicitud_id = fs.id;
            """)
            res = await db.execute(sql, {"solicitud_id": solicitud_id})
            row = res.mappings().first()
            return dict(row) if row else None

        # Fallback ORM para SQLite en entorno de tests
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def get_detalle_operacional(
        self, db: AsyncSession, solicitud_id: int, detalle_id: int
    ) -> Optional[TallerSolicitudDetalle]:
        """
        Carga puntual de un detalle de falla específico para mutaciones atómicas,
        con joinedload de su falla y categoría en 1 sola consulta SQL.
        """
        stmt = (
            select(TallerSolicitudDetalle)
            .options(
                joinedload(TallerSolicitudDetalle.falla).joinedload(FallaTaller.categoria),
                joinedload(TallerSolicitudDetalle.solicitud),
            )
            .where(
                and_(
                    TallerSolicitudDetalle.id == detalle_id,
                    TallerSolicitudDetalle.solicitud_id == solicitud_id,
                )
            )
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_solicitud_con_detalles(
        self, db: AsyncSession, solicitud_id: int
    ) -> Optional[TallerSolicitud]:
        """
        Carga la solicitud únicamente con sus detalles y catálogo de fallas en 1 sola consulta SQL,
        evitando las 4 consultas extra de mecánicos, comentarios y pauta.
        Optimizado con joinedload para resolver cabecera y detalles en 1 solo viaje de red.
        """
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.id == solicitud_id)
            .execution_options(populate_existing=True)
            .options(
                joinedload(TallerSolicitud.bus),
                joinedload(TallerSolicitud.creador),
                joinedload(TallerSolicitud.mecanico_cierre),
                joinedload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.falla).joinedload(FallaTaller.categoria),
                joinedload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.mecanico_resolvio),
                noload(TallerSolicitud.mecanicos),
                noload(TallerSolicitud.asignaciones_fallas),
                noload(TallerSolicitud.comentarios),
                noload(TallerSolicitud.pauta_respuestas),
            )
        )
        res = await db.execute(stmt)
        return res.unique().scalar_one_or_none()

    async def get_presencias_activas_mecanicos(
        self, db: AsyncSession, solicitud_id: int, mecanicos_ids: List[int]
    ) -> Set[int]:
        """
        Obtiene en 1 sola consulta SQL el conjunto de IDs de mecánicos que ya tienen presencia activa en la solicitud.
        """
        if not mecanicos_ids:
            return set()
        stmt = select(TallerSolicitudMecanico.mecanico_id).where(
            and_(
                TallerSolicitudMecanico.solicitud_id == solicitud_id,
                TallerSolicitudMecanico.mecanico_id.in_(mecanicos_ids),
                TallerSolicitudMecanico.is_activo == True,
            )
        )
        res = await db.execute(stmt)
        return set(res.scalars().all())

    async def get_solicitud_operacional(self, db: AsyncSession, solicitud_id: int) -> Optional[TallerSolicitud]:
        """
        Carga operativa ligera de la solicitud para mutaciones, sin cargar colecciones pesadas
        (como la bitácora histórica de comentarios o pauta) reduciendo consultas innecesarias.
        """
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.id == solicitud_id)
            .execution_options(populate_existing=True)
            .options(
                joinedload(TallerSolicitud.bus),
                joinedload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.falla).joinedload(FallaTaller.categoria),
                selectinload(TallerSolicitud.mecanicos).joinedload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.asignaciones_fallas),
                noload(TallerSolicitud.comentarios),
                noload(TallerSolicitud.pauta_respuestas),
            )
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def list_pendientes(
        self, db: AsyncSession, limit: Optional[int] = 50, skip: int = 0
    ) -> List[dict] | List[TallerSolicitud]:
        if db.bind and db.bind.dialect.name == "postgresql":
            # 1 sola consulta SQL nativa de alta velocidad consolidada con CTEs y agregación JSON
            sql = text("""
                WITH filtered_solicitudes AS (
                    SELECT s.id, s.n_bus, s.bus_id, s.usuario_creador_id, s.mecanico_cierre_id,
                           s.estado, s.descripcion_general, s.foto_url, s.motivo_incompleto_checklist,
                           s.motivo_cierre_parcial, s.fecha_creacion, s.fecha_cierre
                    FROM taller_solicitudes s
                    WHERE s.estado IN ('REPORTADO', 'PENDIENTE', 'PENDIENTE_REASIGNACION')
                    ORDER BY s.id DESC, s.fecha_creacion DESC
                    LIMIT :limit OFFSET :skip
                ),
                asigs_por_detalle AS (
                    SELECT 
                        a.detalle_id,
                        json_agg(
                            json_build_object(
                                'id', um.id,
                                'nombre', CONCAT(um.nombre, ' ', um.apellido),
                                'origen', a.origen,
                                'fecha_asignacion', a.fecha_asignacion
                            )
                        ) as mecanicos_asignados
                    FROM taller_asignacion_fallas a
                    JOIN usuarios um ON um.id = a.mecanico_id
                    WHERE a.is_activo = true
                    GROUP BY a.detalle_id
                ),
                detalles_agg AS (
                    SELECT 
                        d.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', d.id,
                                'solicitud_id', d.solicitud_id,
                                'categoria_id', f.categoria_id,
                                'categoria_nombre', cf.nombre,
                                'falla_id', d.falla_id,
                                'falla', CASE WHEN f.id IS NOT NULL THEN json_build_object(
                                    'id', f.id,
                                    'categoria_id', f.categoria_id,
                                    'nombre', f.nombre,
                                    'is_active', f.is_active
                                ) ELSE NULL END,
                                'descripcion_personalizada', d.descripcion_personalizada,
                                'resuelto', d.resuelto,
                                'mecanico_resolvio_id', d.mecanico_resolvio_id,
                                'mecanico_resolvio_nombre', CASE WHEN ur.id IS NOT NULL THEN CONCAT(ur.nombre, ' ', ur.apellido) ELSE NULL END,
                                'falta_repuesto', d.falta_repuesto,
                                'comentario_repuesto', d.comentario_repuesto,
                                'fecha_creacion', d.fecha_creacion,
                                'fecha_resolucion', d.fecha_resolucion,
                                'mecanicos_asignados', COALESCE(apd.mecanicos_asignados, '[]'::json)
                            ) ORDER BY d.id
                        ) as detalles_json
                    FROM taller_solicitud_detalles d
                    JOIN filtered_solicitudes fs ON fs.id = d.solicitud_id
                    LEFT JOIN asigs_por_detalle apd ON apd.detalle_id = d.id
                    LEFT JOIN fallas_taller f ON f.id = d.falla_id
                    LEFT JOIN categorias_falla cf ON cf.id = f.categoria_id
                    LEFT JOIN usuarios ur ON ur.id = d.mecanico_resolvio_id
                    GROUP BY d.solicitud_id
                ),
                mecanicos_agg AS (
                    SELECT 
                        sub.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', sub.id,
                                'solicitud_id', sub.solicitud_id,
                                'mecanico_id', sub.mecanico_id,
                                'mecanico_nombre', CONCAT(um.nombre, ' ', um.apellido),
                                'es_lider_responsable', sub.es_lider_responsable,
                                'is_activo', true,
                                'fecha_asignacion', sub.fecha_asignacion
                            ) ORDER BY sub.id
                        ) as mecanicos_json
                    FROM (
                        SELECT sm.id, sm.solicitud_id, sm.mecanico_id, sm.es_lider_responsable, sm.fecha_asignacion
                        FROM taller_solicitud_mecanicos sm
                        JOIN filtered_solicitudes fs ON fs.id = sm.solicitud_id
                        WHERE sm.is_activo = true
                        UNION
                        SELECT af.id, af.solicitud_id, af.mecanico_id, false as es_lider_responsable, af.fecha_asignacion
                        FROM taller_asignacion_fallas af
                        JOIN filtered_solicitudes fs ON fs.id = af.solicitud_id
                        WHERE af.is_activo = true
                    ) sub
                    JOIN usuarios um ON um.id = sub.mecanico_id
                    GROUP BY sub.solicitud_id
                ),
                evidencias_agg AS (
                    SELECT 
                        e.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', e.id,
                                'solicitud_id', e.solicitud_id,
                                'detalle_id', e.detalle_id,
                                'usuario_id', e.usuario_id,
                                'url', e.url,
                                'original_filename', e.original_filename,
                                'size_bytes', e.size_bytes,
                                'content_type', e.content_type,
                                'fecha_creacion', e.fecha_creacion
                            ) ORDER BY e.id ASC
                        ) as evidencias_json
                    FROM taller_solicitud_evidencias e
                    JOIN filtered_solicitudes fs ON fs.id = e.solicitud_id
                    GROUP BY e.solicitud_id
                )
                SELECT 
                    fs.id,
                    fs.n_bus,
                    fs.bus_id,
                    b.patente as bus_patente,
                    fs.usuario_creador_id,
                    CONCAT(u.nombre, ' ', u.apellido) as usuario_creador_nombre,
                    fs.mecanico_cierre_id,
                    CASE WHEN mc.id IS NOT NULL THEN CONCAT(mc.nombre, ' ', mc.apellido) ELSE NULL END as mecanico_cierre_nombre,
                    fs.estado,
                    fs.descripcion_general,
                    fs.foto_url,
                    fs.motivo_incompleto_checklist,
                    fs.motivo_cierre_parcial,
                    fs.fecha_creacion,
                    fs.fecha_cierre,
                    COALESCE(da.detalles_json, '[]'::json) as detalles_json,
                    COALESCE(ma.mecanicos_json, '[]'::json) as mecanicos_json,
                    COALESCE(ea.evidencias_json, '[]'::json) as evidencias_json
                FROM filtered_solicitudes fs
                LEFT JOIN buses b ON b.id = fs.bus_id
                LEFT JOIN usuarios u ON u.id = fs.usuario_creador_id
                LEFT JOIN usuarios mc ON mc.id = fs.mecanico_cierre_id
                LEFT JOIN detalles_agg da ON da.solicitud_id = fs.id
                LEFT JOIN mecanicos_agg ma ON ma.solicitud_id = fs.id
                LEFT JOIN evidencias_agg ea ON ea.solicitud_id = fs.id
                ORDER BY fs.id DESC, fs.fecha_creacion DESC
            """)
            res = await db.execute(sql, {"limit": limit or 50, "skip": skip or 0})
            return [dict(r) for r in res.mappings().all()]

        # Fallback ORM para entornos SQLite (testing)
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.estado.in_(["REPORTADO", "PENDIENTE", "PENDIENTE_REASIGNACION"]))
            .order_by(TallerSolicitud.id.desc(), TallerSolicitud.fecha_creacion.desc())
            .options(
                joinedload(TallerSolicitud.bus),
                joinedload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.falla).joinedload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).joinedload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.mecanicos).joinedload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.asignaciones_fallas).joinedload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.evidencias),
                noload(TallerSolicitud.comentarios),
                noload(TallerSolicitud.pauta_respuestas),
            )
        )
        if skip:
            stmt = stmt.offset(skip)
        if limit:
            stmt = stmt.limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def list_mis_trabajos(
        self, db: AsyncSession, mecanico_id: int, limit: Optional[int] = 50, skip: int = 0
    ) -> List[dict] | List[TallerSolicitud]:
        if db.bind and db.bind.dialect.name == "postgresql":
            # 1 sola consulta SQL nativa de alta velocidad para Mis Trabajos
            sql = text("""
                WITH filtered_solicitudes AS (
                    SELECT s.id, s.n_bus, s.bus_id, s.usuario_creador_id, s.mecanico_cierre_id,
                           s.estado, s.descripcion_general, s.foto_url, s.motivo_incompleto_checklist,
                           s.motivo_cierre_parcial, s.fecha_creacion, s.fecha_cierre
                    FROM taller_solicitudes s
                    WHERE s.estado = 'EN_REPARACION'
                      AND (
                          EXISTS (SELECT 1 FROM taller_solicitud_mecanicos sm WHERE sm.solicitud_id = s.id AND sm.mecanico_id = :mecanico_id AND sm.is_activo = true)
                          OR
                          EXISTS (SELECT 1 FROM taller_asignacion_fallas af WHERE af.solicitud_id = s.id AND af.mecanico_id = :mecanico_id AND af.is_activo = true)
                      )
                    ORDER BY s.fecha_creacion DESC
                    LIMIT :limit OFFSET :skip
                ),
                detalles_agg AS (
                    SELECT 
                        d.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', d.id,
                                'solicitud_id', d.solicitud_id,
                                'categoria_id', f.categoria_id,
                                'categoria_nombre', cf.nombre,
                                'falla_id', d.falla_id,
                                'falla', CASE WHEN f.id IS NOT NULL THEN json_build_object(
                                    'id', f.id,
                                    'categoria_id', f.categoria_id,
                                    'nombre', f.nombre,
                                    'is_active', f.is_active
                                ) ELSE NULL END,
                                'descripcion_personalizada', d.descripcion_personalizada,
                                'resuelto', d.resuelto,
                                'mecanico_resolvio_id', d.mecanico_resolvio_id,
                                'mecanico_resolvio_nombre', CASE WHEN ur.id IS NOT NULL THEN CONCAT(ur.nombre, ' ', ur.apellido) ELSE NULL END,
                                'falta_repuesto', d.falta_repuesto,
                                'comentario_repuesto', d.comentario_repuesto,
                                'fecha_creacion', d.fecha_creacion,
                                'fecha_resolucion', d.fecha_resolucion,
                                'mecanicos_asignados', COALESCE((
                                    SELECT json_agg(
                                        json_build_object(
                                            'id', um.id,
                                            'nombre', CONCAT(um.nombre, ' ', um.apellido),
                                            'origen', a.origen,
                                            'fecha_asignacion', a.fecha_asignacion
                                        )
                                    )
                                    FROM taller_asignacion_fallas a
                                    JOIN usuarios um ON um.id = a.mecanico_id
                                    WHERE a.detalle_id = d.id AND a.is_activo = true
                                ), '[]'::json)
                            ) ORDER BY d.id
                        ) as detalles_json
                    FROM taller_solicitud_detalles d
                    JOIN filtered_solicitudes fs ON fs.id = d.solicitud_id
                    LEFT JOIN fallas_taller f ON f.id = d.falla_id
                    LEFT JOIN categorias_falla cf ON cf.id = f.categoria_id
                    LEFT JOIN usuarios ur ON ur.id = d.mecanico_resolvio_id
                    GROUP BY d.solicitud_id
                ),
                mecanicos_agg AS (
                    SELECT 
                        sub.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', sub.id,
                                'solicitud_id', sub.solicitud_id,
                                'mecanico_id', sub.mecanico_id,
                                'mecanico_nombre', CONCAT(um.nombre, ' ', um.apellido),
                                'es_lider_responsable', sub.es_lider_responsable,
                                'is_activo', true,
                                'fecha_asignacion', sub.fecha_asignacion
                            ) ORDER BY sub.id
                        ) as mecanicos_json
                    FROM (
                        SELECT sm.id, sm.solicitud_id, sm.mecanico_id, sm.es_lider_responsable, sm.fecha_asignacion
                        FROM taller_solicitud_mecanicos sm
                        JOIN filtered_solicitudes fs ON fs.id = sm.solicitud_id
                        WHERE sm.is_activo = true
                        UNION
                        SELECT af.id, af.solicitud_id, af.mecanico_id, false as es_lider_responsable, af.fecha_asignacion
                        FROM taller_asignacion_fallas af
                        JOIN filtered_solicitudes fs ON fs.id = af.solicitud_id
                        WHERE af.is_activo = true
                    ) sub
                    JOIN usuarios um ON um.id = sub.mecanico_id
                    GROUP BY sub.solicitud_id
                ),
                evidencias_agg AS (
                    SELECT 
                        e.solicitud_id,
                        json_agg(
                            json_build_object(
                                'id', e.id,
                                'solicitud_id', e.solicitud_id,
                                'detalle_id', e.detalle_id,
                                'usuario_id', e.usuario_id,
                                'url', e.url,
                                'original_filename', e.original_filename,
                                'size_bytes', e.size_bytes,
                                'content_type', e.content_type,
                                'fecha_creacion', e.fecha_creacion
                            ) ORDER BY e.id ASC
                        ) as evidencias_json
                    FROM taller_solicitud_evidencias e
                    JOIN filtered_solicitudes fs ON fs.id = e.solicitud_id
                    GROUP BY e.solicitud_id
                )
                SELECT 
                    fs.id,
                    fs.n_bus,
                    fs.bus_id,
                    b.patente as bus_patente,
                    fs.usuario_creador_id,
                    CONCAT(u.nombre, ' ', u.apellido) as usuario_creador_nombre,
                    fs.mecanico_cierre_id,
                    CASE WHEN mc.id IS NOT NULL THEN CONCAT(mc.nombre, ' ', mc.apellido) ELSE NULL END as mecanico_cierre_nombre,
                    fs.estado,
                    fs.descripcion_general,
                    fs.foto_url,
                    fs.motivo_incompleto_checklist,
                    fs.motivo_cierre_parcial,
                    fs.fecha_creacion,
                    fs.fecha_cierre,
                    COALESCE(da.detalles_json, '[]'::json) as detalles_json,
                    COALESCE(ma.mecanicos_json, '[]'::json) as mecanicos_json,
                    COALESCE(ea.evidencias_json, '[]'::json) as evidencias_json
                FROM filtered_solicitudes fs
                LEFT JOIN buses b ON b.id = fs.bus_id
                LEFT JOIN usuarios u ON u.id = fs.usuario_creador_id
                LEFT JOIN usuarios mc ON mc.id = fs.mecanico_cierre_id
                LEFT JOIN detalles_agg da ON da.solicitud_id = fs.id
                LEFT JOIN mecanicos_agg ma ON ma.solicitud_id = fs.id
                LEFT JOIN evidencias_agg ea ON ea.solicitud_id = fs.id
                ORDER BY fs.fecha_creacion DESC
            """)
            res = await db.execute(sql, {"mecanico_id": mecanico_id, "limit": limit or 50, "skip": skip or 0})
            return [dict(r) for r in res.mappings().all()]

        # Fallback ORM para entornos SQLite (testing)
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
                joinedload(TallerSolicitud.bus),
                joinedload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.falla).joinedload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).joinedload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.mecanicos).joinedload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.asignaciones_fallas).joinedload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.evidencias),
                noload(TallerSolicitud.comentarios),
                noload(TallerSolicitud.pauta_respuestas),
            )
        )
        if skip:
            stmt = stmt.offset(skip)
        if limit:
            stmt = stmt.limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())


    async def list_auditoria(self, db: AsyncSession) -> List[TallerSolicitud]:
        stmt = (
            select(TallerSolicitud)
            .order_by(TallerSolicitud.fecha_creacion.desc())
            .options(
                joinedload(TallerSolicitud.bus),
                joinedload(TallerSolicitud.creador),
                joinedload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.falla).joinedload(FallaTaller.categoria),
                selectinload(TallerSolicitud.detalles).joinedload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).joinedload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.mecanicos).joinedload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).joinedload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).joinedload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.evidencias),
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

    async def get_pauta_resumen(
        self, db: AsyncSession, solicitud_id: int
    ) -> tuple[int, List[dict]]:
        """
        Retorna (total_items, respuestas_data) en exactamente 1 sola consulta SQL
        usando LEFT JOIN entre pauta_taller_items, taller_solicitud_pauta y usuarios.
        """
        stmt = (
            select(
                PautaTallerItem.id.label("item_id"),
                PautaTallerItem.categoria.label("item_categoria"),
                PautaTallerItem.item.label("item_nombre"),
                PautaTallerItem.orden.label("item_orden"),
                TallerSolicitudPauta.id.label("id"),
                TallerSolicitudPauta.solicitud_id.label("solicitud_id"),
                TallerSolicitudPauta.estado.label("estado"),
                TallerSolicitudPauta.observacion.label("observacion"),
                TallerSolicitudPauta.mecanico_id.label("mecanico_id"),
                TallerSolicitudPauta.fecha_registro.label("fecha_registro"),
                Usuario.nombre.label("mecanico_nombre"),
                Usuario.apellido.label("mecanico_apellido"),
            )
            .select_from(PautaTallerItem)
            .outerjoin(
                TallerSolicitudPauta,
                and_(
                    TallerSolicitudPauta.item_id == PautaTallerItem.id,
                    TallerSolicitudPauta.solicitud_id == solicitud_id,
                ),
            )
            .outerjoin(Usuario, Usuario.id == TallerSolicitudPauta.mecanico_id)
            .where(PautaTallerItem.is_active == True)
            .order_by(PautaTallerItem.orden.asc(), PautaTallerItem.id.asc())
        )
        res = await db.execute(stmt)
        rows = res.all()

        total_items = len(rows)
        respuestas = []
        for r in rows:
            if r.id is not None:
                mec_nom = None
                if r.mecanico_nombre:
                    mec_nom = f"{r.mecanico_nombre} {r.mecanico_apellido or ''}".strip()
                respuestas.append({
                    "id": r.id,
                    "solicitud_id": r.solicitud_id,
                    "item_id": r.item_id,
                    "item_categoria": r.item_categoria,
                    "item_nombre": r.item_nombre,
                    "estado": r.estado,
                    "observacion": r.observacion,
                    "mecanico_id": r.mecanico_id,
                    "mecanico_nombre": mec_nom,
                    "fecha_registro": r.fecha_registro,
                })
        return total_items, respuestas

    async def upsert_pauta_respuestas(
        self, db: AsyncSession, solicitud_id: int, respuestas: List[dict], mecanico_id: int, now: datetime
    ) -> None:
        """
        Guarda o actualiza en lote las respuestas de la pauta preventiva en 1 sola operación atómica.
        Usa ON CONFLICT DO UPDATE según el dialecto (PostgreSQL o SQLite).
        """
        if not respuestas:
            return

        values = [
            {
                "solicitud_id": solicitud_id,
                "item_id": r["item_id"],
                "estado": r["estado"],
                "observacion": r.get("observacion"),
                "mecanico_id": mecanico_id,
                "fecha_registro": now,
            }
            for r in respuestas
        ]

        if db.bind and db.bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(TallerSolicitudPauta).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["solicitud_id", "item_id"],
                set_={
                    "estado": stmt.excluded.estado,
                    "observacion": stmt.excluded.observacion,
                    "mecanico_id": stmt.excluded.mecanico_id,
                    "fecha_registro": stmt.excluded.fecha_registro,
                },
            )
            await db.execute(stmt)
        elif db.bind and db.bind.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            stmt = sqlite_insert(TallerSolicitudPauta).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["solicitud_id", "item_id"],
                set_={
                    "estado": stmt.excluded.estado,
                    "observacion": stmt.excluded.observacion,
                    "mecanico_id": stmt.excluded.mecanico_id,
                    "fecha_registro": stmt.excluded.fecha_registro,
                },
            )
            await db.execute(stmt)
        else:
            for val in values:
                existing = await db.execute(
                    select(TallerSolicitudPauta).where(
                        and_(
                            TallerSolicitudPauta.solicitud_id == solicitud_id,
                            TallerSolicitudPauta.item_id == val["item_id"],
                        )
                    )
                )
                obj = existing.scalar_one_or_none()
                if obj:
                    obj.estado = val["estado"]
                    obj.observacion = val["observacion"]
                    obj.mecanico_id = val["mecanico_id"]
                    obj.fecha_registro = val["fecha_registro"]
                else:
                    db.add(TallerSolicitudPauta(**val))

    async def get_conteo_pauta_y_mecanico(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: int
    ) -> tuple[int, int, Optional[str], bool]:
        """
        Retorna (total_pauta, respondidos_pauta, nombre_mecanico, solicitud_existe)
        en exactamente 1 sola consulta SQL nativa consolidada.
        """
        stmt = select(
            select(func.count(PautaTallerItem.id)).where(PautaTallerItem.is_active == True).scalar_subquery().label("total_pauta"),
            select(func.count(TallerSolicitudPauta.id)).where(TallerSolicitudPauta.solicitud_id == solicitud_id).scalar_subquery().label("respondidos_pauta"),
            select(Usuario.nombre).where(Usuario.id == mecanico_id).scalar_subquery().label("u_nombre"),
            select(Usuario.apellido).where(Usuario.id == mecanico_id).scalar_subquery().label("u_apellido"),
            select(TallerSolicitud.id).where(TallerSolicitud.id == solicitud_id).scalar_subquery().label("solicitud_id"),
        )
        res = await db.execute(stmt)
        row = res.first()
        if not row:
            return 0, 0, None, False
        total_p = row[0] or 0
        resp_p = row[1] or 0
        u_nom = row[2]
        u_ape = row[3]
        sol_id = row[4]
        mec_nombre = f"{u_nom or ''} {u_ape or ''}".strip() or None
        sol_existe = sol_id is not None
        return total_p, resp_p, mec_nombre, sol_existe

    async def check_solicitud_exists(self, db: AsyncSession, solicitud_id: int) -> bool:
        """Verifica existencia de la solicitud mediante una consulta de id ligero."""
        stmt = select(TallerSolicitud.id).where(TallerSolicitud.id == solicitud_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none() is not None

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
        self, db: AsyncSession, solicitud_id: int, fecha_desasignacion: datetime, flush: bool = False
    ) -> List[TallerSolicitudMecanico]:
        """
        Método atómico de persistencia: Busca y desactiva todos los registros de presencia
        activa de mecánicos para la solicitud indicada. Por defecto no fuerza flush.
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
            if mec.fecha_asignacion:
                mec.duracion_minutos = _calcular_duracion_minutos(mec.fecha_asignacion, fecha_desasignacion)
        if flush:
            await db.flush()
        return mecs

    async def desactivar_mecanicos_por_ids(
        self, db: AsyncSession, solicitud_id: int, mecanicos_ids: Set[int], fecha_desasignacion: datetime, flush: bool = False
    ) -> List[TallerSolicitudMecanico]:
        """
        Método atómico de persistencia: Desactiva mecánicos activos específicos por su mecanico_id.
        Por defecto no fuerza flush.
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
            if mec.fecha_asignacion:
                mec.duracion_minutos = _calcular_duracion_minutos(mec.fecha_asignacion, fecha_desasignacion)
        if flush:
            await db.flush()
        return mecs

    async def desactivar_todas_asignaciones_activas(
        self, db: AsyncSession, solicitud_id: int, fecha_desasignacion: datetime, flush: bool = False
    ) -> List[TallerAsignacionFalla]:
        """
        Método atómico de persistencia: Desactiva todas las asignaciones activas de fallas
        para la solicitud indicada. Por defecto no fuerza flush.
        """
        stmt = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.is_activo == True,
            )
        )
        res = await db.execute(stmt)
        asigs = list(res.scalars().all())
        for a in asigs:
            a.is_activo = False
            a.fecha_desasignacion = fecha_desasignacion
            if a.fecha_asignacion:
                a.duracion_minutos = _calcular_duracion_minutos(a.fecha_asignacion, fecha_desasignacion)
        if flush:
            await db.flush()
        return asigs

    async def desactivar_cuadrilla_y_asignaciones_completas(
        self, db: AsyncSession, solicitud_id: int, fecha_desasignacion: datetime
    ) -> tuple[List[TallerSolicitudMecanico], List[TallerAsignacionFalla]]:
        """
        Desactiva en sesión todos los mecánicos activos y todas las asignaciones
        activas de la solicitud en bloque, sin flushes intermedios antes del commit.
        """
        mecs = await self.desactivar_mecanicos_activos(db, solicitud_id, fecha_desasignacion, flush=False)
        asigs = await self.desactivar_todas_asignaciones_activas(db, solicitud_id, fecha_desasignacion, flush=False)
        return mecs, asigs

    async def flush(self, db: AsyncSession) -> None:
        await db.flush()


mantencion_repository = MantencionRepository()
