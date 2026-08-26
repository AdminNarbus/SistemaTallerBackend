from typing import List, Optional, Union
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bus import Bus


def es_bus_permitido(n_bus_val: Optional[Union[str, int]]) -> bool:
    """
    Valida si un número de bus está permitido según las reglas de negocio:
    - n_bus debe estar entre 300 y 900 inclusive (300 <= n_bus <= 900),
    - O bien ser la excepción número '10' / 10.
    """
    if n_bus_val is None:
        return False
    s_val = str(n_bus_val).strip()
    if s_val == "10":
        return True
    if s_val.isdigit():
        num = int(s_val)
        return 300 <= num <= 900
    return False


async def buscar_numeros_por_prefijo(
    db: AsyncSession,
    n_bus: Optional[Union[str, int]] = None,
    limit: Optional[int] = None,
) -> List[Union[int, str]]:
    """
    Busca en la tabla public.buses todos los números de bus (n_bus) que:
    1. Empiecen con el prefijo indicado en el payload (si existe).
    2. Cumplan con la condición de negocio: (300 <= n_bus <= 900) o (n_bus == 10).
    Retorna la lista ordenada de manera ascendente numéricamente.
    """
    stmt = select(distinct(Bus.n_bus)).where(
        Bus.n_bus.isnot(None), Bus.n_bus != ""
    )

    if n_bus is not None:
        search_term = str(n_bus).strip()
        if search_term:
            stmt = stmt.where(Bus.n_bus.like(f"{search_term}%"))

    if limit is not None:
        stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    numeros_raw = result.scalars().all()

    resultado: List[Union[int, str]] = []
    for num in numeros_raw:
        if num is not None and es_bus_permitido(num):
            s_num = str(num).strip()
            if s_num.isdigit():
                resultado.append(int(s_num))
            else:
                resultado.append(s_num)

    def sort_key(val: Union[int, str]):
        if isinstance(val, int):
            return (0, val)
        s_val = str(val).strip()
        if s_val.isdigit():
            return (0, int(s_val))
        return (1, s_val)

    resultado.sort(key=sort_key)
    return resultado


async def buscar_buses_por_prefijo(
    db: AsyncSession,
    n_bus: Optional[Union[str, int]] = None,
    limit: Optional[int] = None,
) -> List[Bus]:
    """
    Busca los objetos completos Bus en la BD por prefijo de n_bus filtrando por rango y excepción.
    """
    stmt = select(Bus)

    if n_bus is not None:
        search_term = str(n_bus).strip()
        if search_term:
            stmt = stmt.where(Bus.n_bus.like(f"{search_term}%"))

    if limit is not None:
        stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    buses_raw = list(result.scalars().all())

    buses = [b for b in buses_raw if b.n_bus and es_bus_permitido(b.n_bus)]

    def bus_sort_key(b: Bus):
        if b.n_bus and str(b.n_bus).strip().isdigit():
            return (0, int(str(b.n_bus).strip()))
        return (1, b.n_bus or "")

    buses.sort(key=bus_sort_key)
    return buses


async def buscar_numeros_buses(
    db: AsyncSession,
    q: Optional[str] = None,
    limit: int = 100,
) -> List[str]:
    """
    Busca y devuelve una lista ordenada con los números de buses (n_bus) de la BD.
    """
    stmt = select(distinct(Bus.n_bus)).where(
        Bus.n_bus.isnot(None), Bus.n_bus != ""
    )

    if q and str(q).strip():
        search_term = f"%{str(q).strip()}%"
        stmt = stmt.where(Bus.n_bus.ilike(search_term))

    if limit is not None:
        stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    numeros_raw = [str(x) for x in result.scalars().all() if x is not None]

    numeros = [x for x in numeros_raw if es_bus_permitido(x)]

    def sort_key(val: str):
        s_val = val.strip()
        if s_val.isdigit():
            return (0, int(s_val))
        return (1, s_val)

    numeros.sort(key=sort_key)
    return numeros
