from datetime import datetime
import json
import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_current_user,
    require_mecanico_or_admin,
    require_conductor_or_supervisor_or_admin,
)
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.taller.constants import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_PAGE_SKIP,
    MAX_PAGE_LIMIT,
)
from app.modules.taller.dtos import (
    SolicitudCreateDTO,
    SolicitudDetalleCreateDTO,
    SolicitudDTO,
    SolicitudResumenDTO,
)
from app.modules.taller.services.solicitud_service import solicitud_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _extraer_datos_multipart_solicitud(
    form: Any,
) -> tuple[SolicitudCreateDTO, Optional[Any], List[Any]]:
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
                logger.warning("[MANTENCION] Error al parsear detalles JSON en multipart: %s", e)
        elif isinstance(detalles_raw, list):
            detalles = [SolicitudDetalleCreateDTO(**d) for d in detalles_raw]

    dto = SolicitudCreateDTO(
        n_bus=n_bus,
        bus_id=bus_id,
        bus_patente=bus_patente,
        descripcion_general=descripcion_general,
        foto_url=foto_url,
        detalles=detalles,
    )
    return dto, foto_file, fotos_files


@router.post("/solicitudes", response_model=SolicitudDTO, status_code=status.HTTP_201_CREATED)
async def create_solicitud(
    request: Request,
    current_user: UsuarioResponseDTO = Depends(require_conductor_or_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Crea una nueva solicitud de mantención de taller.
    Soporta dos modalidades de consumo en 1 solo request HTTP:
    1. application/json: Envío estándar de SolicitudCreateDTO con foto_url (opcional).
    2. multipart/form-data: Envío directo del formulario y archivos fotográficos adjuntos ('foto'/'evidencias').
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
            dto = SolicitudCreateDTO(**body)
    except ValidationError as ve:
        raise RequestValidationError(ve.errors())

    logger.info(
        "[MANTENCION] Creando solicitud de mantención | creador_id=%s | rol='%s' | n_bus='%s' | cant_fotos_adjuntas=%s",
        current_user.id,
        current_user.rol,
        dto.n_bus,
        len(fotos_files),
    )
    return await solicitud_service.create_solicitud(
        db,
        dto,
        creador_id=current_user.id,
        creador_nombre=current_user.nombre_completo,
        creador_rol=current_user.rol,
        foto=foto_file,
        fotos=fotos_files,
    )


@router.get("/pendientes", response_model=List[SolicitudResumenDTO])
async def list_pendientes(
    response: Response,
    skip: int = Query(DEFAULT_PAGE_SKIP, ge=0, description="Número de solicitudes a omitir para paginación"),
    limit: Optional[int] = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Límite de solicitudes a retornar (default: 20)"),
    fecha_modificacion_desde: Optional[datetime] = Query(None, description="Fecha/hora mínima de última modificación (ISO 8601)"),
    fecha_modificacion_hasta: Optional[datetime] = Query(None, description="Fecha/hora máxima de última modificación (ISO 8601)"),
    fecha_desde: Optional[datetime] = Query(None, description="Alias de fecha_modificacion_desde"),
    fecha_hasta: Optional[datetime] = Query(None, description="Alias de fecha_modificacion_hasta"),
    estado: Optional[str] = Query(None, description="Filtro opcional por estado ('PENDIENTE', 'EN_REPARACION')"),
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Pestaña 1 Mecánico: Buses esperando o en atención en taller (PENDIENTE / EN_REPARACION, default: 20 por página)."""
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
    f_desde = fecha_modificacion_desde or fecha_desde
    f_hasta = fecha_modificacion_hasta or fecha_hasta
    total = await solicitud_service.count_pendientes(
        db, fecha_desde=f_desde, fecha_hasta=f_hasta, estado=estado
    )
    response.headers["X-Total-Count"] = str(total)
    return await solicitud_service.list_pendientes(
        db, limit=limit, skip=skip, fecha_desde=f_desde, fecha_hasta=f_hasta, estado=estado
    )


@router.get("/mis-trabajos", response_model=List[SolicitudResumenDTO])
async def list_mis_trabajos(
    response: Response,
    skip: int = Query(DEFAULT_PAGE_SKIP, ge=0, description="Número de solicitudes a omitir para paginación"),
    limit: Optional[int] = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Límite de solicitudes a retornar (default: 20)"),
    fecha_modificacion_desde: Optional[datetime] = Query(None, description="Fecha/hora mínima de última modificación (ISO 8601)"),
    fecha_modificacion_hasta: Optional[datetime] = Query(None, description="Fecha/hora máxima de última modificación (ISO 8601)"),
    fecha_desde: Optional[datetime] = Query(None, description="Alias de fecha_modificacion_desde"),
    fecha_hasta: Optional[datetime] = Query(None, description="Alias de fecha_modificacion_hasta"),
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Pestaña 2 Mecánico: Buses asignados activamente al mecánico que realiza la consulta (default: 20 por página)."""
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
    f_desde = fecha_modificacion_desde or fecha_desde
    f_hasta = fecha_modificacion_hasta or fecha_hasta
    total = await solicitud_service.count_mis_trabajos(
        db, mecanico_id=current_user.id, fecha_desde=f_desde, fecha_hasta=f_hasta
    )
    response.headers["X-Total-Count"] = str(total)
    return await solicitud_service.list_mis_trabajos(
        db, mecanico_id=current_user.id, limit=limit, skip=skip, fecha_desde=f_desde, fecha_hasta=f_hasta
    )


@router.get("/{id}", response_model=SolicitudDTO)
async def get_solicitud(
    id: int,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Obtiene el detalle completo de una solicitud por su ID."""
    logger.debug("[MANTENCION] Consultando solicitud id=%s por usuario_id=%s", id, current_user.id)
    return await solicitud_service.get_solicitud(db, id)
