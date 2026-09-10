import logging
from typing import Any, List, Optional
from sqlalchemy import select
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
        solo_flota_taller: bool = False,
    ) -> List[Bus]:
        """
        Retorna la lista completa de entidades Bus ordenadas por n_bus.
        (Nota: Si solo_flota_taller=True se aplica la regla de dominio correspondiente).
        """
        stmt = select(Bus)
        if solo_activos:
            stmt = stmt.where(Bus.is_active == True)
        stmt = stmt.order_by(Bus.n_bus.asc())
        result = await db.execute(stmt)
        buses = list(result.scalars().all())

        if solo_flota_taller:
            from app.modules.buses.services.bus_service import es_bus_operativo_taller
            buses = [b for b in buses if es_bus_operativo_taller(b.n_bus)]

        return buses

    async def buscar_por_prefijo(
        self,
        db: AsyncSession,
        prefix: str = "",
        solo_activos: bool = True,
    ) -> List[Bus]:
        """
        Consulta SQL pura para filtrar buses cuyo número inicie con el prefijo dado.
        Retorna las entidades Bus coincidentes sin aplicar reglas de negocio de presentación.
        """
        clean_prefix = (prefix or "").strip()
        stmt = select(Bus)
        if solo_activos:
            stmt = stmt.where(Bus.is_active == True)
        if clean_prefix:
            stmt = stmt.where(Bus.n_bus.like(f"{clean_prefix}%"))
        stmt = stmt.order_by(Bus.n_bus.asc())

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def buscar_n_buses_por_prefijo(
        self,
        db: AsyncSession,
        prefix: str = "",
        solo_activos: bool = True,
        solo_flota_taller: bool = True,
    ) -> Any:
        """
        Método de compatibilidad con llamadas existentes.
        Delega a la orquestación en BusService.
        """
        from app.modules.buses.services.bus_service import bus_service
        return await bus_service.buscar_sugerencias_buses(
            db, query=prefix, solo_flota_taller=solo_flota_taller
        )

    async def buscar_buses(
        self, db: AsyncSession, term: str = ""
    ) -> Any:
        """Método de compatibilidad con llamadas existentes."""
        return await self.buscar_n_buses_por_prefijo(db, prefix=term)

    async def update_en_taller_directo(
        self, db: AsyncSession, bus_id: int, en_taller: bool
    ) -> Optional[Bus]:
        """
        Actualiza directamente el estado en_taller en una sola sentencia UPDATE con RETURNING,
        evitando consultas SELECT previas o flush intermedio.
        """
        from sqlalchemy import update
        stmt = (
            update(Bus)
            .where(Bus.id == bus_id)
            .values(en_taller=en_taller)
            .returning(Bus)
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def update_en_taller(
        self, db: AsyncSession, bus_or_id: Any, en_taller: bool
    ) -> Optional[Bus]:
        """
        Actualiza el estado en_taller del bus.
        Acepta tanto la entidad Bus cargada como un bus_id numérico.
        """
        if isinstance(bus_or_id, Bus):
            bus_or_id.en_taller = en_taller
            return bus_or_id
        return await self.update_en_taller_directo(db, int(bus_or_id), en_taller)


bus_repository = BusRepository()


