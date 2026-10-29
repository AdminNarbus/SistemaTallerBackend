from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_mecanico_or_admin
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.taller.dtos.bus_mecanico_dto import AgregarFallaBusDTO, BusesMecanicoFiltroDTO, BusMecanicoDTO
from app.modules.taller.dtos.solicitud_dto import SolicitudDTO
from app.modules.taller.services.buses_taller_service import RegistroFallaBus, buses_taller_service

router = APIRouter(prefix="/buses")


@router.get("", response_model=list[BusMecanicoDTO])
async def listar_buses_mecanico(
    response: Response,
    filtros: Annotated[BusesMecanicoFiltroDTO, Query()],
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Una fila por bus: OT pendiente/en reparación, OT liberada y sin OT vigente."""
    buses, total = await buses_taller_service.listar(db, filtros)
    response.headers["X-Total-Count"] = str(total)
    response.headers["Cache-Control"] = "no-store"
    return buses


@router.post("/{bus_id}/fallas", response_model=SolicitudDTO, status_code=status.HTTP_201_CREATED)
async def agregar_falla_bus(
    dto: AgregarFallaBusDTO,
    bus_id: int = Path(..., ge=1),
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Añade una falla a la OT vigente o crea la OT; autoasignación opcional."""
    return await buses_taller_service.agregar_falla(db, RegistroFallaBus(bus_id, current_user, dto))
