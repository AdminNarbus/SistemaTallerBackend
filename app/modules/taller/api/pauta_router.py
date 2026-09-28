import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_current_user, require_mecanico_or_admin
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.taller.dtos import (
    PautaBatchUpdateDTO,
    PautaEstadoResumenDTO,
)
from app.modules.taller.services.pauta_service import pauta_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{id}/pauta", response_model=PautaEstadoResumenDTO)
async def get_pauta_solicitud(
    id: int,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Retorna el estado de completitud y respuestas de la pauta preventiva para una solicitud."""
    return await pauta_service.get_pauta_resumen(db, solicitud_id=id)


@router.post("/{id}/pauta", response_model=PautaEstadoResumenDTO)
async def guardar_respuestas_pauta(
    id: int,
    dto: PautaBatchUpdateDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Registra o actualiza en lote respuestas a los ítems de la pauta preventiva."""
    logger.info(
        "[MANTENCION] Guardando respuestas de pauta en solicitud_id=%s | mecanico_id=%s | total_respuestas=%s",
        id,
        current_user.id,
        len(dto.respuestas),
    )
    return await pauta_service.guardar_respuestas_pauta(
        db, solicitud_id=id, dto=dto, mecanico_id=current_user.id
    )
