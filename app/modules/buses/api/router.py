import logging
from typing import List, Optional
from fastapi import APIRouter, Body, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.modules.auth.dtos import UsuarioResponseDTO
from app.modules.buses.dtos import (
    BusAutocompleteDTO,
    BusResponseDTO,
    BusSimpleDTO,
    BusUpdateEnTallerDTO,
)
from app.modules.buses.services.bus_service import bus_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/buscar",
    response_model=List[BusSimpleDTO],
    summary="Buscar sugerencias de buses por prefijo",
    description="Devuelve una lista ordenada de BusSimpleDTO (id, n_bus, patente, en_taller) que inicien con el prefijo especificado en 'query'. Por defecto filtra vehículos fuera del rango 200 <= n_bus < 900.",
)
async def buscar_buses(
    response: Response,
    query: Optional[str] = Query(None, description="Prefijo o término de búsqueda para n_bus"),
    solo_flota_taller: bool = Query(True, description="Excluir vehículos fuera del rango 200 <= n_bus < 900"),
    db: AsyncSession = SessionDep,
) -> List[BusSimpleDTO]:
    response.headers["Cache-Control"] = "private, max-age=120, stale-while-revalidate=60"
    return await bus_service.buscar_sugerencias_buses(
        db, query=query, solo_flota_taller=solo_flota_taller
    )


@router.get(
    "",
    response_model=List[BusAutocompleteDTO],
    summary="Listar todos los buses activos",
    description="Devuelve el catálogo de buses activos con información básica de autocompletado y selección.",
)
async def listar_buses(
    response: Response,
    solo_activos: bool = Query(True, description="Filtrar solo buses activos"),
    solo_flota_taller: bool = Query(True, description="Excluir vehículos fuera del rango 200 <= n_bus < 900"),
    db: AsyncSession = SessionDep,
) -> List[BusAutocompleteDTO]:
    response.headers["Cache-Control"] = "private, max-age=120, stale-while-revalidate=60"
    return await bus_service.listar_buses(
        db, solo_activos=solo_activos, solo_flota_taller=solo_flota_taller
    )


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


@router.patch(
    "/{bus_id}/en-taller",
    response_model=BusResponseDTO,
    summary="Actualizar estado en taller de un bus",
    description="Permite a la supervisora o administradores marcar si un bus está físicamente en taller para reparaciones.",
)
async def actualizar_en_taller(
    bus_id: int = Path(..., description="ID numérico del bus", ge=1),
    payload: BusUpdateEnTallerDTO = Body(...),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> BusResponseDTO:
    logger.info(
        "[BUSES] Solicitud de cambio en_taller | bus_id=%s | en_taller=%s | supervisor_id=%s",
        bus_id,
        payload.en_taller,
        current_user.id,
    )
    return await bus_service.actualizar_en_taller(
        db, bus_id=bus_id, en_taller=payload.en_taller, motivo=payload.motivo
    )


