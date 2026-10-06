import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_mecanico_or_admin,
    require_mecanico_or_supervisor_or_admin,
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
from app.modules.taller.api.request_parsers import parse_json_or_multipart

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
    request: Request,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """Agrega un comentario JSON o multipart con hasta tres imágenes a la bitácora."""
    dto, fotos = await parse_json_or_multipart(request, ComentarioCreateDTO)
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
        fotos=fotos,
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
