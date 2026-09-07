from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, get_current_user
from app.modules.auth.models.usuario import Usuario
from app.modules.neumaticos.dtos import (
    FormularioNeumaticoResponseDTO,
    FormularioNeumaticoStatusDTO,
    ReporteNeumaticoCreateDTO,
    ReporteNeumaticoResponseDTO,
)
from app.modules.neumaticos.services.formulario_neumatico_service import (
    formulario_neumatico_service,
)

router = APIRouter()


@router.get(
    "/formularioNeumatico",
    response_model=FormularioNeumaticoStatusDTO,
    summary="Obtener/consultar formulario de neumáticos",
    response_description="Respuesta exitosa de recepción",
)
async def obtener_formulario_neumatico():
    """
    Endpoint HTTP: Consulta el estado de disponibilidad del formulario de neumáticos.
    Delega directamente al servicio la obtención del estado.
    """
    return await formulario_neumatico_service.obtener_estado_formulario()


@router.post(
    "/formularioNeumatico",
    response_model=FormularioNeumaticoResponseDTO,
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
    current_user: Optional[Usuario] = Depends(get_current_user),
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP: Recibe los datos multipart del formulario de neumáticos.
    Responsabilidades:
    - Extrae el user_id del token JWT (current_user) con fallback al usuario_id provisto.
    - Encapsula los campos de entrada en un ReporteNeumaticoCreateDTO.
    - Invoca al servicio para orquestar la persistencia y reglas de negocio.
    - Retorna el FormularioNeumaticoResponseDTO tipado.
    """
    effective_user_id = current_user.id if current_user else usuario_id

    dto = ReporteNeumaticoCreateDTO(
        usuario_id=effective_user_id,
        maquina=maquina,
        tipo_bus=tipo_bus,
        ruedas=ruedas,
        motivo=motivo,
        precio=precio,
        marca_fuego=marca_fuego,
    )

    return await formulario_neumatico_service.procesar_formulario(
        db=db,
        dto=dto,
        evidencia=evidencia,
        usuario_id=effective_user_id,
    )


@router.get(
    "/reportes/{id}",
    response_model=ReporteNeumaticoResponseDTO,
    summary="Obtener reporte de neumático por ID",
    response_description="Detalle del reporte de neumático",
)
async def get_reporte_neumatico_by_id(
    id: int,
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP: Obtiene el detalle de un reporte de neumático específico por su ID.
    """
    return await formulario_neumatico_service.get_reporte_by_id(db=db, reporte_id=id)
