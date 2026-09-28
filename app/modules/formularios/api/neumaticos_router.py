import logging
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, get_current_user
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.formularios.dtos.neumaticos_dto import (
    FormularioNeumaticoResponseDTO,
    FormularioNeumaticoStatusDTO,
    ReporteNeumaticoCreateDTO,
    ReporteNeumaticoPaginadoDTO,
    ReporteNeumaticoResponseDTO,
)
from app.modules.formularios.services.formulario_neumatico_service import (
    formulario_neumatico_service,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/formularioNeumatico",
    response_model=FormularioNeumaticoStatusDTO,
    summary="Obtener/consultar formulario de neumáticos",
    response_description="Respuesta exitosa de recepción",
)
@router.get(
    "/neumaticos/estado",
    response_model=FormularioNeumaticoStatusDTO,
    summary="Consultar estado del formulario de neumáticos",
    include_in_schema=True,
)
async def obtener_formulario_neumatico():
    """
    Endpoint HTTP: Consulta el estado de disponibilidad del formulario de neumáticos.
    Delega directamente al servicio la obtención del estado.
    """
    return await formulario_neumatico_service.obtener_estado_formulario()


@router.post(
    "/neumaticos",
    response_model=FormularioNeumaticoResponseDTO,
    summary="Enviar formulario de neumáticos",
    status_code=status.HTTP_200_OK,
    response_description="Respuesta exitosa de procesamiento",
)
@router.post(
    "/formularioNeumatico",
    response_model=FormularioNeumaticoResponseDTO,
    include_in_schema=False,
)
async def enviar_formulario_neumatico(
    usuario_id: Optional[int] = Form(None),
    maquina: Optional[str] = Form(None),
    ruedas: Optional[str] = Form(None),
    motivo: Optional[str] = Form(None),
    marca_fuego: Optional[str] = Form(None),
    evidencia: Optional[UploadFile] = File(None),
    current_user: Optional[UsuarioResponseDTO] = Depends(get_current_user),
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP: Recibe los datos multipart del formulario de neumáticos.
    Responsabilidades:
    - Extrae el user_id del token JWT (current_user) con fallback al usuario_id provisto.
    - Encapsula los campos de entrada en un ReporteNeumaticoCreateDTO (marca_fuego opcional).
    - Invoca al servicio para orquestar la persistencia y reglas de negocio.
    - Retorna el FormularioNeumaticoResponseDTO tipado.
    """
    effective_user_id = current_user.id if current_user else usuario_id

    logger.info(
        "Recibida solicitud POST /neumaticos | usuario_id_efectivo=%s | maquina=%s | con_evidencia=%s",
        effective_user_id,
        maquina,
        bool(evidencia and evidencia.filename),
    )

    dto = ReporteNeumaticoCreateDTO(
        usuario_id=effective_user_id,
        maquina=maquina,
        ruedas=ruedas,
        motivo=motivo,
        marca_fuego=marca_fuego,
    )

    return await formulario_neumatico_service.procesar_formulario(
        db=db,
        dto=dto,
        evidencia=evidencia,
        usuario_id=effective_user_id,
    )


@router.get(
    "/neumaticos/reportes",
    response_model=ReporteNeumaticoPaginadoDTO,
    summary="Listar reportes de neumáticos paginados",
    response_description="Listado paginado de reportes de neumáticos para supervisión",
)
@router.get(
    "/reportes",
    response_model=ReporteNeumaticoPaginadoDTO,
    include_in_schema=False,
)
async def listar_reportes_neumaticos(
    response: Response,
    page: int = Query(1, ge=1, description="Número de página (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Cantidad de registros por página"),
    n_bus: Optional[str] = Query(None, description="Filtro opcional por número de máquina/bus"),
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP: Consulta el listado paginado de reportes de neumáticos.
    Soporta filtrado por número de máquina/bus y expone cabecera X-Total-Count para interfaces de supervisión.
    """
    resultado = await formulario_neumatico_service.listar_reportes(
        db=db, page=page, page_size=page_size, n_bus=n_bus
    )
    response.headers["X-Total-Count"] = str(resultado.total)
    return resultado


@router.get(
    "/neumaticos/reportes/{id}",
    response_model=ReporteNeumaticoResponseDTO,
    summary="Obtener reporte de neumático por ID",
    response_description="Detalle del reporte de neumático",
)
@router.get(
    "/reportes/{id}",
    response_model=ReporteNeumaticoResponseDTO,
    include_in_schema=False,
)
async def get_reporte_neumatico_by_id(
    id: int,
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP: Obtiene el detalle de un reporte de neumático específico por su ID.
    """
    logger.debug("Consultando reporte de neumático por ID=%s", id)
    return await formulario_neumatico_service.get_reporte_by_id(db=db, reporte_id=id)

