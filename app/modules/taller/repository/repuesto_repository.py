"""Consultas para el catálogo y los repuestos utilizados."""
from sqlalchemy import func, or_, select

from app.modules.taller.models.repuesto import Repuesto
from app.modules.taller.models.taller_repuesto_utilizado import TallerRepuestoUtilizado
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle


class RepuestoRepository:
    async def listar_catalogo(self, db, q, incluir_inactivos, skip, limit):
        filtros = [] if incluir_inactivos else [Repuesto.is_active.is_(True)]
        if q:
            patron = f"%{q}%"
            filtros.append(or_(Repuesto.codigo.ilike(patron), Repuesto.nombre.ilike(patron), Repuesto.parte.ilike(patron)))
        total = await db.scalar(select(func.count()).select_from(Repuesto).where(*filtros))
        filas = await db.scalars(select(Repuesto).where(*filtros).order_by(Repuesto.nombre, Repuesto.id).offset(skip).limit(limit))
        return list(filas), total

    async def listar_usos(self, db, solicitud_id, detalle_id, incluir_anulados, skip, limit):
        filtros = [TallerSolicitudDetalle.solicitud_id == solicitud_id]
        if detalle_id is not None:
            filtros.append(TallerRepuestoUtilizado.falla_detalle_id == detalle_id)
        if not incluir_anulados:
            filtros.append(TallerRepuestoUtilizado.fecha_anulacion.is_(None))
        base = select(TallerRepuestoUtilizado).join(TallerSolicitudDetalle, TallerSolicitudDetalle.id == TallerRepuestoUtilizado.falla_detalle_id).where(*filtros)
        total = await db.scalar(select(func.count()).select_from(base.subquery()))
        filas = await db.scalars(base.order_by(TallerRepuestoUtilizado.id).offset(skip).limit(limit))
        return list(filas), total

    async def uso_vigente(self, db, detalle_id, repuesto_id):
        return await db.scalar(select(TallerRepuestoUtilizado).where(TallerRepuestoUtilizado.falla_detalle_id == detalle_id, TallerRepuestoUtilizado.repuesto_id == repuesto_id, TallerRepuestoUtilizado.fecha_anulacion.is_(None)))

    async def existe_uso(self, db, detalle_id):
        return await db.scalar(select(TallerRepuestoUtilizado.id).where(TallerRepuestoUtilizado.falla_detalle_id == detalle_id).limit(1)) is not None


repuesto_repository = RepuestoRepository()
