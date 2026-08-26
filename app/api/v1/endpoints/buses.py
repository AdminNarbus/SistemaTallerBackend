from typing import List, Optional, Union
from fastapi import APIRouter, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.crud.crud_bus import buscar_numeros_por_prefijo
from app.schemas.bus import BusSearchPayload

router = APIRouter()


@router.post(
    "/buscar",
    response_model=List[Union[int, str]],
    status_code=status.HTTP_200_OK,
    summary="Buscar números de buses por prefijo (Payload JSON)",
    response_description="Lista simple con los n_bus que empiezan por el prefijo (ej: [501, 56, 59])",
)
@router.post(
    "/",
    response_model=List[Union[int, str]],
    status_code=status.HTTP_200_OK,
    summary="Buscar números de buses por prefijo (Endpoint raíz POST)",
    include_in_schema=False,
)
async def buscar_buses_payload(
    payload: Optional[BusSearchPayload] = None,
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP POST: Recibe un payload JSON con `n_bus` o vacío.
    Retorna directamente la lista de los números de bus (n_bus) que empiezan con el número proporcionado.
    - Ejemplo: payload {"n_bus": 5} -> Retorna [501, 56, 59]
    - Ejemplo: payload {"n_bus": "12"} -> Retorna [12, 120, 124]
    - Ejemplo: payload vacio {} -> Retorna todos los n_bus.
    """
    search_term = payload.get_search_term() if payload else None
    numeros = await buscar_numeros_por_prefijo(db=db, n_bus=search_term)
    return numeros


@router.get(
    "/buscar",
    response_model=List[Union[int, str]],
    status_code=status.HTTP_200_OK,
    summary="Buscar números de buses por prefijo (Query Parameter)",
)
@router.get(
    "/",
    response_model=List[Union[int, str]],
    status_code=status.HTTP_200_OK,
    summary="Listar números de buses",
)
async def buscar_buses_query(
    n_bus: Optional[str] = Query(
        None, description="Número o prefijo del bus (ej: 5, 12)"
    ),
    q: Optional[str] = Query(None, description="Alias para n_bus"),
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP GET: Permite buscar números de buses filtrando por n_bus en la query string (ej: ?n_bus=5).
    """
    term = n_bus if n_bus is not None else q
    numeros = await buscar_numeros_por_prefijo(db=db, n_bus=term)
    return numeros