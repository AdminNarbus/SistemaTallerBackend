from typing import List, Optional
from fastapi import APIRouter, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.modules.buses.dtos.bus_dto import BusAutocompleteDTO, BusResponseDTO
from app.modules.buses.services.bus_service import bus_service

router = APIRouter()


@router.get(
    "/buscar",
    response_model=List[str],
    summary="Buscar sugerencias de números de bus por prefijo",
    description="Devuelve una lista ordenada de n_bus que inicien con el prefijo especificado en 'query'. Si está vacío, devuelve todos los buses activos.",
)
async def buscar_buses(
    query: Optional[str] = Query(None, description="Prefijo o término de búsqueda para n_bus"),
    db: AsyncSession = SessionDep,
) -> List[str]:
    return await bus_service.buscar_sugerencias_buses(db, query=query)


@router.get(
    "",
    response_model=List[BusAutocompleteDTO],
    summary="Listar todos los buses activos",
    description="Devuelve el catálogo de buses activos con información básica de autocompletado y selección.",
)
async def listar_buses(
    solo_activos: bool = Query(True, description="Filtrar solo buses activos"),
    db: AsyncSession = SessionDep,
) -> List[BusAutocompleteDTO]:
    return await bus_service.listar_buses(db, solo_activos=solo_activos)


@router.get(
    "/{bus_id}",
    response_model=BusResponseDTO,
    summary="Obtener detalles de un bus por ID",
    description="Devuelve la ficha completa y atributos del bus.",
)
async def get_bus_por_id(
    bus_id: int = Path(..., description="ID numérico del bus", ge=1),
    db: AsyncSession = SessionDep,
) -> BusResponseDTO:
    return await bus_service.get_bus_by_id(db, bus_id=bus_id)


@router.get(
    "/numero/{n_bus}",
    response_model=BusResponseDTO,
    summary="Obtener detalles de un bus por n_bus",
    description="Devuelve la ficha completa del bus a partir de su número de máquina asignado.",
)
async def get_bus_por_numero(
    n_bus: str = Path(..., description="Número de bus (ej. '339')"),
    db: AsyncSession = SessionDep,
) -> BusResponseDTO:
    return await bus_service.get_bus_by_n_bus(db, n_bus=n_bus)

