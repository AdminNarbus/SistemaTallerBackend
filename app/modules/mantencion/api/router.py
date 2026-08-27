from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.modules.mantencion.dtos.taller_solicitud_dto import SolicitudMantencionCreateDTO
from app.modules.mantencion.services.formulario_mantencion_service import (
    formulario_mantencion_service,
)

router = APIRouter()


@router.post(
    "/solicitudTaller",
    summary="Enviar solicitud de mantención de taller",
    status_code=status.HTTP_201_CREATED,
    response_description="Solicitud procesada y almacenada en taller_solicitudes",
)
async def crear_solicitud_taller(
    payload: SolicitudMantencionCreateDTO,
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP POST para recepcionar formularios de mantención de taller.
    """
    return await formulario_mantencion_service.procesar_solicitud(payload=payload, db=db)
