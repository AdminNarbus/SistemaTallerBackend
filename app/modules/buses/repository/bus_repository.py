from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.buses.models.bus import Bus


class BusRepository:
    """Repositorio para consultas y lógica de persistencia de Buses."""

    async def buscar_buses(
        self, db: AsyncSession, term: str = ""
    ) -> List[str]:
        """
        Filtra buses cuyo n_bus cumpla:
        - Estar dentro del rango 300..900 O ser el bus 10.
        - Coincidir con el término buscado.
        - Ordenados de manera numérica ascendente.
        """
        term_clean = term.strip()

        stmt = select(Bus.n_bus)
        result = await db.execute(stmt)
        n_buses_raw = result.scalars().all()

        buses_filtrados: List[int] = []

        for nb in n_buses_raw:
            if not nb:
                continue
            s_nb = str(nb).strip()
            if not s_nb:
                continue

            if term_clean and not s_nb.startswith(term_clean):
                continue

            try:
                val = int(s_nb)
                if (300 <= val <= 900) or (val == 10):
                    buses_filtrados.append(val)
            except ValueError:
                continue

        buses_filtrados.sort()
        return [str(val) for val in buses_filtrados]


bus_repository = BusRepository()
