import logging
from typing import List, Optional
from fastapi import APIRouter, Body, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.modules.auth.dtos import UsuarioResponseDTO
from app.modules.buses.dtos import (
    BusAutocompleteDTO,
    BusCreateDTO,
    BusDarDeBajaDTO,
    BusResponseDTO,
    BusSimpleDTO,
    BusUpdateEnTallerDTO,
)

from app.modules.buses.constants import (
    DEFAULT_PAGE_SKIP,
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
)
from app.modules.buses.services.bus_service import bus_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/buscar",
    response_model=List[BusSimpleDTO],
    summary="Buscar sugerencias de buses por prefijo",
    description="Devuelve una lista ordenada de BusSimpleDTO (id, n_bus, patente, en_taller) que inicien con el prefijo especificado en 'query'.",
)
async def buscar_buses(
    response: Response,
    query: Optional[str] = Query(None, description="Prefijo o término de búsqueda para n_bus"),
    solo_flota_taller: bool = Query(True, description="Filtrar vehículos con número de máquina asignado"),
    limit: Optional[int] = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Tope de sugerencias a retornar (default: 20)"),
    db: AsyncSession = SessionDep,
) -> List[BusSimpleDTO]:
    response.headers["Cache-Control"] = "private, max-age=120, stale-while-revalidate=60"
    return await bus_service.buscar_sugerencias_buses(
        db, query=query, solo_flota_taller=solo_flota_taller, limit=limit
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
    solo_flota_taller: bool = Query(True, description="Filtrar vehículos con número de máquina asignado"),
    skip: int = Query(DEFAULT_PAGE_SKIP, ge=0, description="Cantidad de registros a omitir"),
    limit: Optional[int] = Query(None, ge=1, le=MAX_PAGE_LIMIT, description="Límite de registros a retornar"),
    db: AsyncSession = SessionDep,
) -> List[BusAutocompleteDTO]:
    response.headers["Cache-Control"] = "private, max-age=120, stale-while-revalidate=60"
    total = await bus_service.count_buses(db, solo_activos=solo_activos)
    response.headers["X-Total-Count"] = str(total)
    return await bus_service.listar_buses(
        db,
        solo_activos=solo_activos,
        solo_flota_taller=solo_flota_taller,
        skip=skip,
        limit=limit,
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


@router.post(
    "",
    response_model=BusResponseDTO,
    status_code=201,
    summary="Agregar nuevo bus a la flota",
    description="Permite a la supervisora o administradores registrar un nuevo bus con marcas de tiempo de creación.",
)
async def create_bus(
    payload: BusCreateDTO = Body(...),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> BusResponseDTO:
    logger.info(
        "[BUSES] Registrando nuevo bus | patente='%s' | n_bus='%s' | supervisor_id=%s",
        payload.patente,
        payload.n_bus,
        current_user.id,
    )
    return await bus_service.create_bus(db, dto=payload, usuario_id=current_user.id)


@router.patch(
    "/{bus_id}/dar-de-baja",
    response_model=BusResponseDTO,
    summary="Dar de baja a un bus",
    description="Desactiva un bus de la flota (is_active=False) registrando motivo, fecha_baja y supervisor. Valida que no tenga OTs activas a menos que se fuerce.",
)
async def dar_de_baja_bus(
    bus_id: int = Path(..., description="ID numérico del bus", ge=1),
    payload: BusDarDeBajaDTO = Body(default_factory=BusDarDeBajaDTO),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> BusResponseDTO:
    logger.info(
        "[BUSES] Solicitud dar de baja bus | bus_id=%s | motivo='%s' | forzar=%s | supervisor_id=%s",
        bus_id,
        payload.motivo,
        payload.forzar,
        current_user.id,
    )
    return await bus_service.dar_de_baja_bus(
        db, bus_id=bus_id, dto=payload, usuario_id=current_user.id
    )


@router.delete(
    "/{bus_id}",
    response_model=BusResponseDTO,
    summary="Dar de baja a un bus (DELETE alias)",
    description="Alias HTTP DELETE para dar de baja a un bus desactivándolo lógicamente.",
)
async def dar_de_baja_bus_delete(
    bus_id: int = Path(..., description="ID numérico del bus", ge=1),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> BusResponseDTO:
    logger.info(
        "[BUSES] DELETE dar de baja bus | bus_id=%s | supervisor_id=%s",
        bus_id,
        current_user.id,
    )
    return await bus_service.dar_de_baja_bus(
        db, bus_id=bus_id, dto=BusDarDeBajaDTO(), usuario_id=current_user.id
    )


@router.patch(
    "/{bus_id}/reactivar",
    response_model=BusResponseDTO,
    summary="Reactivar un bus dado de baja",
    description="Restaura un bus previamente dado de baja a estado activo (is_active=True) y limpia marcas de baja.",
)
async def reactivar_bus(
    bus_id: int = Path(..., description="ID numérico del bus", ge=1),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> BusResponseDTO:
    logger.info(
        "[BUSES] Reactivando bus | bus_id=%s | supervisor_id=%s",
        bus_id,
        current_user.id,
    )
    return await bus_service.reactivar_bus(
        db, bus_id=bus_id, usuario_id=current_user.id
    )

