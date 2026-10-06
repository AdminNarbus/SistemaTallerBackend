import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_mecanico_or_admin,
    require_mecanico_or_supervisor_or_admin,
)
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.taller.dtos import (
    AgregarFallaDTO,
    CheckFallaDTO,
    DetalleUpdateDTO,
    ReportarRepuestoDTO,
    SolicitudDTO,
)
from app.modules.taller.constants import EstadoFalla
from app.modules.taller.services.averias_service import averias_service
from app.modules.taller.api.request_parsers import parse_json_or_multipart

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolver_check_params(
    dto: Optional[CheckFallaDTO],
    resuelto_query: Optional[bool],
    mecanico_query: Optional[int],
) -> tuple[Optional[EstadoFalla], Optional[str], Optional[bool], Optional[int]]:
    """Extrae y consolida los parámetros de resolución priorizando el DTO JSON."""
    estado = dto.estado if dto else None
    motivo_incompleto = dto.motivo_incompleto if dto else None
    resuelto = (
        dto.resuelto
        if (dto and dto.resuelto is not None)
        else (resuelto_query if resuelto_query is not None else None)
    )
    mecanico_id = (dto.effective_mecanico_id if dto else None) or mecanico_query
    return estado, motivo_incompleto, resuelto, mecanico_id


@router.post("/{id}/detalles", response_model=SolicitudDTO, status_code=status.HTTP_201_CREATED)
async def agregar_falla(
    id: int,
    dto: AgregarFallaDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """Permite a un mecánico o supervisor agregar una nueva avería detectada durante la atención."""
    logger.info(
        "[MANTENCION] Agregando nueva avería en solicitud_id=%s | mecanico_id=%s | falla_id=%s",
        id,
        current_user.id,
        dto.falla_id,
    )
    return await averias_service.agregar_falla(
        db, solicitud_id=id, mecanico_id=current_user.id, dto=dto
    )


@router.patch("/{id}/detalles/{detalle_id}/check", response_model=DetalleUpdateDTO)
async def check_detalle(
    id: int,
    detalle_id: int,
    request: Request,
    resuelto: Optional[bool] = Query(None, description="Parámetro alternativo de resolución"),
    mecanico_id: Optional[int] = Query(None, description="ID del mecánico resolutor alternativo"),
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """Marca una falla; acepta JSON legado o multipart con fotos opcionales."""
    dto, fotos = await parse_json_or_multipart(request, CheckFallaDTO)
    estado_final, motivo_final, resuelto_final, resolutor_id = _resolver_check_params(dto, resuelto, mecanico_id)

    logger.info(
        "[MANTENCION] Check falla en sol_id=%s | det_id=%s | estado=%s | resuelto=%s | actor_id=%s | resolutor_id=%s",
        id,
        detalle_id,
        estado_final,
        resuelto_final,
        current_user.id,
        resolutor_id,
    )
    return await averias_service.check_detalle(
        db=db,
        solicitud_id=id,
        detalle_id=detalle_id,
        mecanico_id=current_user.id,
        resuelto=resuelto_final,
        mecanico_nombre=current_user.nombre_completo,
        mecanico_resolvio_id=resolutor_id,
        estado=estado_final,
        motivo_incompleto=motivo_final,
        comentario=dto.comentario,
        fotos=fotos,
    )


@router.patch("/{id}/detalles/{detalle_id}/repuesto", response_model=DetalleUpdateDTO)
async def reportar_repuesto(
    id: int,
    detalle_id: int,
    dto: ReportarRepuestoDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Reporta si una falla no puede continuar por falta de repuestos."""
    logger.info(
        "[MANTENCION] Reportando repuesto en solicitud_id=%s | detalle_id=%s | falta_repuesto=%s",
        id,
        detalle_id,
        dto.falta_repuesto,
    )
    return await averias_service.reportar_repuesto(
        db,
        solicitud_id=id,
        detalle_id=detalle_id,
        dto=dto,
        mecanico_id=current_user.id,
        mecanico_nombre=current_user.nombre_completo,
    )
