from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.taller.models.taller_ubicacion import Ciudad, Taller


class TallerUbicacionRepository:
    async def ciudades(self, db: AsyncSession) -> list[Ciudad]:
        return list((await db.scalars(select(Ciudad).order_by(Ciudad.nombre, Ciudad.id))).all())

    async def ciudad_por_codigo(self, db: AsyncSession, codigo: str) -> Ciudad | None:
        return await db.scalar(select(Ciudad).where(func.lower(Ciudad.codigo) == codigo.lower()))

    async def ciudad(self, db: AsyncSession, ciudad_id: int) -> Ciudad | None:
        return await db.get(Ciudad, ciudad_id)

    async def talleres(self, db: AsyncSession, filtros: dict):
        stmt = select(Taller).order_by(Taller.nombre, Taller.id)
        if filtros.get("ciudad_id"):
            stmt = stmt.where(Taller.ciudad_id == filtros["ciudad_id"])
        if filtros.get("tipo"):
            stmt = stmt.where(Taller.tipo == filtros["tipo"])
        if filtros.get("is_activo") is not None:
            stmt = stmt.where(Taller.is_activo == filtros["is_activo"])
        if filtros.get("q"):
            stmt = stmt.where(Taller.nombre.ilike(f"%{filtros['q'].strip()}%"))
        total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        return list((await db.scalars(stmt.offset(filtros["skip"]).limit(filtros["limit"]))).all()), total or 0

    async def taller(self, db: AsyncSession, taller_id: int) -> Taller | None:
        return await db.get(Taller, taller_id)


taller_ubicacion_repository = TallerUbicacionRepository()
