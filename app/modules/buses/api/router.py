from typing import List, Optional
from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.modules.buses.repository.bus_repository import bus_repository

router = APIRouter()


@router.get(
    "/buscar",
    response_model=List[str],
    summary="Buscar números de buses de forma ascendente",
    description="Filtra buses en rango 300..900 y la excepción 10, ordenados de forma ascendente.",
)
async def buscar_buses(
    query: Optional[str] = Query(None, description="Término para filtrar por prefijo de n_bus"),
    db: AsyncSession = SessionDep,
) -> List[str]:
    """
    Retorna la lista de n_buses en formato string ascendente.
    """
    return await bus_repository.buscar_buses(db, term=query or "")
