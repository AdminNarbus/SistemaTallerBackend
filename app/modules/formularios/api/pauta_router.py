import logging
from typing import List
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_current_user, require_mecanico_or_admin
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.formularios.dtos.pauta_dto import (
    PautaBatchUpdateDTO,
    PautaEstadoResumenDTO,
    PautaTallerItemDTO,
)
from app.modules.formularios.services.formulario_pauta_service import (
    formulario_pauta_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/pauta/items", response_model=List[PautaTallerItemDTO])
async def get_pauta_items(
    response: Response,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Retorna el catálogo maestro de 10 ítems de inspección preventiva de taller."""
    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=60"
    return await formulario_pauta_service.get_pauta_items(db)


@router.get("/pauta/solicitudes/{id}", response_model=PautaEstadoResumenDTO)
@router.get("/solicitudes/{id}/pauta", response_model=PautaEstadoResumenDTO, include_in_schema=False)
async def get_pauta_solicitud(
    id: int,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Retorna el estado de completitud y respuestas de la pauta preventiva para una solicitud."""
    return await formulario_pauta_service.get_pauta_resumen(db, solicitud_id=id)


@router.post("/pauta/solicitudes/{id}", response_model=PautaEstadoResumenDTO)
@router.post("/solicitudes/{id}/pauta", response_model=PautaEstadoResumenDTO, include_in_schema=False)
async def guardar_respuestas_pauta(
    id: int,
    dto: PautaBatchUpdateDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Registra o actualiza en lote respuestas a los ítems de la pauta preventiva."""
    logger.info(
        "[PAUTA] Guardando respuestas de pauta en solicitud_id=%s | mecanico_id=%s | total_respuestas=%s",
        id,
        current_user.id,
        len(dto.respuestas),
    )
    return await formulario_pauta_service.guardar_respuestas_pauta(
        db, solicitud_id=id, dto=dto, mecanico_id=current_user.id
    )
