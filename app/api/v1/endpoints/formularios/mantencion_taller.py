from fastapi import APIRouter, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.schemas.taller_solicitud import SolicitudMantencionCreate
from app.services.formulario_mantencion_service import (
    formulario_mantencion_service,
)

router = APIRouter()


@router.get(
    "/formularioMantencionTaller",
    summary="Consultar formulario de mantención taller",
    response_description="Estado del formulario de mantención taller",
)
async def obtener_formulario_mantencion_taller():
    """
    Endpoint GET para consultar disponibilidad del formulario de mantención taller.
    """
    return {
        "status": "success",
        "message": "Solicitud de formularioMantencionTaller recibida correctamente",
        "data": None,
    }


@router.post(
    "/formularioMantencionTaller",
    summary="Enviar solicitud o reporte de mantención taller",
    status_code=status.HTTP_200_OK,
    response_description="Respuesta exitosa de procesamiento y guardado en BD",
)
async def enviar_formulario_mantencion_taller(
    payload: SolicitudMantencionCreate,
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP POST: Recibe el payload JSON del frontend y persiste
    la solicitud en la tabla taller_solicitudes de PostgreSQL narbus_local.
    """
    resultado = await formulario_mantencion_service.procesar_solicitud(
        payload=payload,
        db=db,
    )
    return resultado
