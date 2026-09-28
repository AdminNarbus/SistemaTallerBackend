import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_current_user,
    require_mecanico_or_admin,
    require_supervisor_or_admin,
)
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.taller.dtos import (
    CambiarEstadoSolicitudDTO,
    ComentarioAddedDTO,
    ComentarioCreateDTO,
    FinalizarSolicitudDTO,
    LiberarSolicitudDTO,
    SolicitudDTO,
)
from app.modules.taller.services.cierre_service import cierre_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.patch("/{id}/estado", response_model=SolicitudDTO)
async def cambiar_estado_solicitud(
    id: int,
    dto: CambiarEstadoSolicitudDTO,
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Cambio de estado administrativo de una Orden de Trabajo (OT) exclusivo para supervisores y administradores.
    Permite transicionar entre cualquier estado canónico registrando un comentario justificativo en la bitácora inmutable.
    """
    logger.info(
        "[MANTENCION] Supervisora id=%s cambiando estado de solicitud_id=%s a %s",
        current_user.id,
        id,
        dto.estado,
    )
    return await cierre_service.cambiar_estado_solicitud(
        db,
        solicitud_id=id,
        dto=dto,
        supervisor_id=current_user.id,
        supervisor_nombre=current_user.nombre_completo,
    )


@router.post("/{id}/comentarios", response_model=ComentarioAddedDTO)
async def agregar_comentario(
    id: int,
    dto: ComentarioCreateDTO,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Agrega un comentario a la bitácora independiente de la solicitud."""
    logger.info(
        "[MANTENCION] Agregando comentario en solicitud_id=%s | usuario_id=%s",
        id,
        current_user.id,
    )
    return await cierre_service.agregar_comentario(
        db,
        solicitud_id=id,
        usuario_id=current_user.id,
        dto=dto,
        usuario_nombre=current_user.nombre_completo,
    )


@router.post("/{id}/finalizar", response_model=SolicitudDTO)
async def finalizar_solicitud(
    id: int,
    dto: FinalizarSolicitudDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Finaliza los trabajos de la solicitud, verifica pauta preventiva y fallas, liberando el bus de taller."""
    logger.info(
        "[MANTENCION] Finalizando solicitud_id=%s | mecanico_cierre_id=%s",
        id,
        current_user.id,
    )
    return await cierre_service.finalizar_solicitud(
        db,
        solicitud_id=id,
        mecanico_cierre_id=current_user.id,
        dto=dto,
        mecanico_cierre_nom=current_user.nombre_completo,
    )


@router.post("/{id}/liberar", response_model=SolicitudDTO)
async def liberar_solicitud(
    id: int,
    dto: LiberarSolicitudDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Cierra y libera el bus de taller. Exige justificación si la pauta está incompleta o si quedan fallas no resueltas."""
    logger.info(
        "[MANTENCION] Liberando bus y cerrando solicitud_id=%s | mecanico_id=%s",
        id,
        current_user.id,
    )
    return await cierre_service.liberar_solicitud(
        db,
        solicitud_id=id,
        dto=dto,
        mecanico_id=current_user.id,
        mecanico_nombre=current_user.nombre_completo,
    )
