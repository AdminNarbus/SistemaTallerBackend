import logging
from typing import List, Optional
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.buses.models.bus import Bus

logger = logging.getLogger(__name__)


class BusRepository:
    """Acceso a datos y persistencia pura de la tabla 'buses' con SQLAlchemy asíncrono."""

    async def get_by_id(self, db: AsyncSession, bus_id: int) -> Optional[Bus]:
        """Obtiene un bus por su clave primaria ID."""
        stmt = select(Bus).where(Bus.id == bus_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_n_bus(self, db: AsyncSession, n_bus: str) -> Optional[Bus]:
        """Obtiene un bus por su número de máquina único."""
        stmt = select(Bus).where(Bus.n_bus == n_bus)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        db: AsyncSession,
        solo_activos: bool = True,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> List[Bus]:
        """
        Retorna entidades Bus desde la base de datos ordenadas por n_bus,
        con soporte de paginación opcional en capa de persistencia.
        """
        stmt = select(Bus)
        if solo_activos:
            stmt = stmt.where(Bus.is_active == True)
        stmt = stmt.order_by(Bus.n_bus.asc()).offset(skip)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_buses(self, db: AsyncSession, solo_activos: bool = True) -> int:
        """Retorna el conteo total de buses registrados."""
        stmt = select(func.count(Bus.id))
        if solo_activos:
            stmt = stmt.where(Bus.is_active == True)
        res = await db.execute(stmt)
        return res.scalar() or 0

    async def buscar_por_prefijo(
        self,
        db: AsyncSession,
        prefix: str = "",
        solo_activos: bool = True,
        limit: Optional[int] = None,
    ) -> List[Bus]:
        """
        Consulta SQL pura para filtrar buses cuyo número inicie con el prefijo dado.
        Retorna las entidades Bus coincidentes ordenadas por n_bus.
        """
        clean_prefix = (prefix or "").strip()
        stmt = select(Bus)
        if solo_activos:
            stmt = stmt.where(Bus.is_active == True)
        if clean_prefix:
            stmt = stmt.where(Bus.n_bus.like(f"{clean_prefix}%"))
        stmt = stmt.order_by(Bus.n_bus.asc())
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_en_taller_directo(
        self, db: AsyncSession, bus_id: int, en_taller: bool
    ) -> Optional[Bus]:
        """
        Actualiza directamente el estado en_taller en una sola sentencia UPDATE con RETURNING,
        evitando consultas SELECT previas o roundtrips redundantes de red.
        """
        stmt = (
            update(Bus)
            .where(Bus.id == bus_id)
            .values(en_taller=en_taller)
            .returning(Bus)
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_patente(self, db: AsyncSession, patente: str) -> Optional[Bus]:
        """Obtiene un bus buscando por patente normalizada en mayúsculas."""
        from sqlalchemy import func

        clean = patente.strip().upper()
        stmt = select(Bus).where(func.upper(Bus.patente) == clean)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def add_bus(self, db: AsyncSession, bus: Bus) -> None:
        """Agrega una nueva entidad Bus a la sesión para persistencia atómica."""
        db.add(bus)

    async def count_solicitudes_activas_por_bus(
        self, db: AsyncSession, bus_id: int
    ) -> int:
        """Cuenta la cantidad de órdenes de trabajo abiertas en taller para el bus dado."""
        from sqlalchemy import func
        from app.modules.mantencion.models.taller_solicitud import TallerSolicitud

        stmt = select(func.count(TallerSolicitud.id)).where(
            TallerSolicitud.bus_id == bus_id,
            TallerSolicitud.estado != "FINALIZADO",
        )
        res = await db.execute(stmt)
        return int(res.scalar() or 0)


bus_repository = BusRepository()

