import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_mecanico_or_admin,
    require_supervisor_or_admin,
)
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.taller.dtos import (
    AgregarColaboradorDTO,
    AsignarFallasSupervisoraDTO,
    AutoasignarFallasDTO,
    LiberarTurnoDTO,
    SolicitudDTO,
    TerminarAvanceDTO,
    TomarTrabajoDTO,
)
from app.modules.taller.services.cuadrilla_service import cuadrilla_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{id}/autoasignar", response_model=SolicitudDTO)
async def autoasignar_fallas(
    id: int,
    dto: AutoasignarFallasDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Autoasignación atómica de fallas por parte de un mecánico.
    Cada mecánico responde únicamente por las fallas específicas que toma.
    Soporta co-responsabilidad: si 2 o más mecánicos toman la misma falla, ambos quedan registrados.
    """
    logger.info(
        "[MANTENCION] Autoasignación de fallas en solicitud_id=%s | mecanico_id=%s | detalles=%s",
        id,
        current_user.id,
        dto.detalles_ids,
    )
    return await cuadrilla_service.autoasignar_fallas(
        db,
        solicitud_id=id,
        dto=dto,
        mecanico_id=current_user.id,
        mecanico_nombre=current_user.nombre_completo,
    )


@router.post("/{id}/asignar", response_model=SolicitudDTO)
async def asignar_fallas_supervisora(
    id: int,
    dto: AsignarFallasSupervisoraDTO,
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Asignación atómica de fallas realizada por la supervisora o administradores a un mecánico específico.
    Permite co-responsabilidad si la falla ya tenía otro mecánico asignado.
    """
    logger.info(
        "[MANTENCION] Supervisora id=%s asignando fallas a mecanico_id=%s en solicitud_id=%s",
        current_user.id,
        dto.mecanico_id,
        id,
    )
    return await cuadrilla_service.asignar_fallas_supervisora(
        db, solicitud_id=id, dto=dto, supervisor_id=current_user.id
    )


@router.post("/{id}/terminar-avance", response_model=SolicitudDTO)
async def terminar_avance(
    id: int,
    dto: TerminarAvanceDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Cierra el turno o avance del mecánico en sus fallas asignadas, registrando la duración en minutos.
    Si ya no quedan mecánicos activos en la solicitud, el estado pasa a PENDIENTE.
    """
    logger.info(
        "[MANTENCION] Mecánico id=%s terminando avance en solicitud_id=%s | comentario='%s'",
        current_user.id,
        id,
        dto.comentario,
    )
    return await cuadrilla_service.terminar_avance(
        db,
        solicitud_id=id,
        dto=dto,
        mecanico_id=current_user.id,
        mecanico_nombre=current_user.nombre_completo,
    )


@router.post("/{id}/tomar", response_model=SolicitudDTO)
async def tomar_trabajo(
    id: int,
    dto: TomarTrabajoDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Auto-asignación de bus + invitación a colaboradores + comentario inicial opcional."""
    logger.info(
        "[MANTENCION] Mecánico id=%s tomando trabajo en solicitud_id=%s | colaboradores=%s",
        current_user.id,
        id,
        dto.colaboradores_ids,
    )
    return await cuadrilla_service.tomar_trabajo(db, solicitud_id=id, mecanico_id=current_user.id, dto=dto)


@router.post("/{id}/desasignarme", response_model=SolicitudDTO)
async def desasignar_mecanico(
    id: int,
    comentario: Optional[str] = Query(None, description="Comentario opcional de salida"),
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Desasignación individual de un mecánico ('[🚪 Salir del Equipo]')."""
    logger.info(
        "[MANTENCION] Mecánico id=%s desasignándose de solicitud_id=%s | comentario='%s'",
        current_user.id,
        id,
        comentario,
    )
    return await cuadrilla_service.desasignar_mecanico(
        db,
        solicitud_id=id,
        mecanico_id=current_user.id,
        comentario=comentario,
        mecanico_nombre=current_user.nombre_completo,
    )


@router.post("/{id}/liberar-turno", response_model=SolicitudDTO)
async def liberar_turno(
    id: int,
    dto: LiberarTurnoDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Liberación / Entrega de turno para el equipo completo ('[🔄 Entregar / Pasar Turno]')."""
    logger.info(
        "[MANTENCION] Usuario id=%s liberando turno completo en solicitud_id=%s",
        current_user.id,
        id,
    )
    return await cuadrilla_service.liberar_turno(
        db,
        solicitud_id=id,
        usuario_id=current_user.id,
        dto=dto,
        usuario_nombre=current_user.nombre_completo,
    )


@router.post("/{id}/agregar-colaborador", response_model=SolicitudDTO)
async def agregar_colaborador(
    id: int,
    dto: AgregarColaboradorDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Agrega un colaborador al equipo mientras la solicitud está EN_REPARACION."""
    logger.info(
        "[MANTENCION] Agregando colaborador_id=%s a solicitud_id=%s por mecanico_id=%s",
        dto.colaborador_id,
        id,
        current_user.id,
    )
    return await cuadrilla_service.agregar_colaborador(db, solicitud_id=id, mecanico_id=current_user.id, dto=dto)
