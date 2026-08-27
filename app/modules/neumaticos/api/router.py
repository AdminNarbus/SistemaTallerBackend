from typing import Optional
from fastapi import APIRouter, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.modules.neumaticos.services.formulario_neumatico_service import (
    formulario_neumatico_service,
)

router = APIRouter()


@router.get(
    "/formularioNeumatico",
    summary="Obtener/consultar formulario de neumáticos",
    response_description="Respuesta exitosa de recepción",
)
async def obtener_formulario_neumatico():
    """
    Endpoint genérico GET para consultar el estado del formulario de neumáticos.
    """
    return {
        "status": "success",
        "message": "Solicitud de formularioNeumatico recibida correctamente",
        "data": None,
    }


@router.post(
    "/formularioNeumatico",
    summary="Enviar formulario de neumáticos",
    status_code=status.HTTP_200_OK,
    response_description="Respuesta exitosa de procesamiento",
)
async def enviar_formulario_neumatico(
    usuario_id: Optional[int] = Form(None),
    maquina: Optional[str] = Form(None),
    tipo_bus: Optional[str] = Form(None),
    ruedas: Optional[str] = Form(None),
    motivo: Optional[str] = Form(None),
    precio: Optional[str] = Form(None),
    marca_fuego: Optional[str] = Form(None),
    evidencia: Optional[UploadFile] = File(None),
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP: Recibe los datos multipart del formulario de neumáticos asociados al usuario_id.
    """
    resultado = await formulario_neumatico_service.procesar_formulario(
        usuario_id=usuario_id,
        maquina=maquina,
        tipo_bus=tipo_bus,
        ruedas=ruedas,
        motivo=motivo,
        precio=precio,
        marca_fuego=marca_fuego,
        evidencia=evidencia,
        db=db,
    )

    return resultado
