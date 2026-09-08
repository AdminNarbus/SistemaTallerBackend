import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.buses.dtos.bus_dto import BusSimpleDTO
from app.modules.buses.models.bus import Bus

logger = logging.getLogger(__name__)


def es_bus_operativo_taller(n_bus: Optional[str]) -> bool:
    """
    Verifica si el número de bus pertenece al rango operativo de buses de pasajeros:
    200 <= n_bus < 900.
    Los vehículos con n_bus < 200 o n_bus >= 900 se excluyen del catálogo operativo de taller.
    """
    if not n_bus:
        return False
    try:
        n = int(str(n_bus).strip())
        return 200 <= n < 900
    except (ValueError, TypeError):
        return False


class BusRepository:
    """Acceso a datos de la tabla 'buses' con SQLAlchemy asíncrono."""

    async def get_by_id(self, db: AsyncSession, bus_id: int) -> Optional[Bus]:
        stmt = select(Bus).where(Bus.id == bus_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_n_bus(self, db: AsyncSession, n_bus: str) -> Optional[Bus]:
        stmt = select(Bus).where(Bus.n_bus == n_bus)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        db: AsyncSession,
        solo_activos: bool = True,
        solo_flota_taller: bool = True,
    ) -> List[Bus]:
        stmt = select(Bus)
        if solo_activos:
            stmt = stmt.where(Bus.is_active == True)
        stmt = stmt.order_by(Bus.n_bus.asc())
        result = await db.execute(stmt)
        buses = list(result.scalars().all())

        if solo_flota_taller:
            buses = [b for b in buses if es_bus_operativo_taller(b.n_bus)]

        return buses

    async def buscar_n_buses_por_prefijo(
        self,
        db: AsyncSession,
        prefix: str = "",
        solo_activos: bool = True,
        solo_flota_taller: bool = True,
    ) -> List[BusSimpleDTO]:
        """
        Filtra buses activos cuyo número inicie con el prefijo dado.
        Retorna una lista de BusSimpleDTO (id, n_bus, patente, en_taller)
        ordenada de manera numérica ascendente.
        Si solo_flota_taller es True, excluye vehículos fuera del rango 200 <= n_bus < 900.
        """
        clean_prefix = prefix.strip()
        stmt = select(Bus.id, Bus.n_bus, Bus.patente, Bus.en_taller)
        if solo_activos:
            stmt = stmt.where(Bus.is_active == True)
        if clean_prefix:
            stmt = stmt.where(Bus.n_bus.like(f"{clean_prefix}%"))
        stmt = stmt.order_by(Bus.n_bus.asc())

        result = await db.execute(stmt)
        rows = result.all()

        buses_filtrados: List[BusSimpleDTO] = []
        vistos = set()
        for row in rows:
            b_id, nb, pat, en_t = row
            if not nb:
                continue
            s_nb = str(nb).strip()
            if not s_nb:
                continue
            if solo_flota_taller and not es_bus_operativo_taller(s_nb):
                continue
            if clean_prefix and not s_nb.startswith(clean_prefix):
                continue
            if b_id in vistos:
                continue
            vistos.add(b_id)
            buses_filtrados.append(
                BusSimpleDTO(
                    id=b_id,
                    n_bus=s_nb,
                    patente=pat,
                    en_taller=bool(en_t),
                )
            )

        # Ordenar numéricamente si es posible, alfabéticamente si no
        def sort_key(dto: BusSimpleDTO):
            try:
                return (0, int(dto.n_bus))
            except ValueError:
                return (1, dto.n_bus)

        buses_filtrados.sort(key=sort_key)
        return buses_filtrados

    async def buscar_buses(
        self, db: AsyncSession, term: str = ""
    ) -> List[BusSimpleDTO]:
        """Método de compatibilidad."""
        return await self.buscar_n_buses_por_prefijo(db, prefix=term)

    async def update_en_taller(
        self, db: AsyncSession, bus_id: int, en_taller: bool
    ) -> Optional[Bus]:
        """Actualiza el estado en_taller del bus con flush atómico en sesión (sin commit)."""
        bus = await self.get_by_id(db, bus_id)
        if not bus:
            return None
        bus.en_taller = en_taller
        await db.flush()
        return bus


bus_repository = BusRepository()


