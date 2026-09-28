import json
import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_conductor_or_supervisor_or_admin,
)
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.formularios.dtos.taller_ingreso_dto import FormularioMantencionCreateDTO
from app.modules.formularios.services.formulario_taller_service import (
    formulario_taller_service,
)
from app.modules.taller.dtos.averias_dto import SolicitudDetalleCreateDTO
from app.modules.taller.dtos.solicitud_dto import SolicitudDTO

logger = logging.getLogger(__name__)

router = APIRouter()


def _extraer_datos_multipart_solicitud(
    form: Any,
) -> tuple[FormularioMantencionCreateDTO, Optional[Any], List[Any]]:
    """Extrae y estructura los campos del formulario multipart y archivos adjuntos."""
    n_bus = form.get("n_bus")
    bus_id_val = form.get("bus_id")
    bus_id = int(bus_id_val) if bus_id_val is not None and str(bus_id_val).isdigit() else None
    bus_patente = form.get("bus_patente")
    descripcion_general = form.get("descripcion_general")
    foto_url = form.get("foto_url")

    fotos_files: List[Any] = []
    for key in ["fotos", "fotos[]", "evidencias", "evidencias[]", "foto", "evidencia"]:
        items = form.getlist(key)
        for item in items:
            if hasattr(item, "filename") and item.filename and item not in fotos_files:
                fotos_files.append(item)

    foto_file = fotos_files[0] if fotos_files else None

    detalles_raw = form.get("detalles")
    detalles = None
    if detalles_raw:
        if isinstance(detalles_raw, str):
            try:
                detalles_list = json.loads(detalles_raw)
                detalles = [SolicitudDetalleCreateDTO(**d) for d in detalles_list]
            except Exception as e:
                logger.warning("[FORMULARIO MANTENCION] Error al parsear detalles JSON en multipart: %s", e)
        elif isinstance(detalles_raw, list):
            detalles = [SolicitudDetalleCreateDTO(**d) for d in detalles_raw]

    dto = FormularioMantencionCreateDTO(
        n_bus=n_bus,
        bus_id=bus_id,
        bus_patente=bus_patente,
        descripcion_general=descripcion_general,
        foto_url=foto_url,
        detalles=detalles,
    )
    return dto, foto_file, fotos_files


@router.post("/taller/solicitudes", response_model=SolicitudDTO, status_code=status.HTTP_201_CREATED)
@router.post("/mantencion/solicitudes", response_model=SolicitudDTO, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/solicitudes", response_model=SolicitudDTO, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_solicitud(
    request: Request,
    current_user: UsuarioResponseDTO = Depends(require_conductor_or_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Endpoint HTTP: Recepción y procesamiento del formulario de ingreso de mantención a taller.
    Soporta JSON y multipart/form-data con subida de evidencias.
    """
    content_type = request.headers.get("content-type", "").lower()
    foto_file = None
    fotos_files: List[Any] = []

    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            dto, foto_file, fotos_files = _extraer_datos_multipart_solicitud(form)
        else:
            body = await request.json()
            dto = FormularioMantencionCreateDTO(**body)
    except ValidationError as ve:
        raise RequestValidationError(ve.errors())

    logger.info(
        "[FORMULARIO MANTENCION] Enviando formulario de ingreso | creador_id=%s | rol='%s' | n_bus='%s' | fotos=%s",
        current_user.id,
        current_user.rol,
        dto.n_bus,
        len(fotos_files),
    )
    return await formulario_taller_service.procesar_formulario_ingreso(
        db=db,
        dto=dto,
        creador_id=current_user.id,
        creador_nombre=current_user.nombre_completo,
        creador_rol=current_user.rol,
        foto=foto_file,
        fotos=fotos_files,
    )
