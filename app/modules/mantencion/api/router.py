import json
import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_current_user,
    require_supervisor_or_admin,
    require_mecanico_or_admin,
    require_conductor_or_admin,
    require_conductor_or_supervisor_or_admin,
    require_mecanico_or_supervisor_or_admin,
)
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos import (
    CategoriaFallaDTO,
    FallaTallerDTO,
    SolicitudDTO,
    SolicitudResumenDTO,
    SolicitudCreateDTO,
    SolicitudDetalleCreateDTO,
    TomarTrabajoDTO,
    LiberarTurnoDTO,
    FinalizarSolicitudDTO,
    ComentarioCreateDTO,
    AgregarColaboradorDTO,
    AutoasignarFallasDTO,
    AsignarFallasSupervisoraDTO,
    CambiarEstadoSolicitudDTO,
    TerminarAvanceDTO,

    ReportarRepuestoDTO,
    PautaTallerItemDTO,
    PautaEstadoResumenDTO,
    PautaBatchUpdateDTO,
    LiberarSolicitudDTO,
    AgregarFallaDTO,
    DetalleUpdateDTO,
    ComentarioAddedDTO,
)

from app.modules.mantencion.constants import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_PAGE_SKIP,
    MAX_PAGE_LIMIT,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mantencion", tags=["mantencion"])


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


@router.get("/pauta/items", response_model=List[PautaTallerItemDTO])
async def get_pauta_items(
    response: Response,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Retorna el catálogo maestro de 11 ítems de inspección preventiva de taller."""
    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=60"
    return await mantencion_service.get_pauta_items(db)


@router.get("/categorias", response_model=List[CategoriaFallaDTO])
async def get_categorias(
    response: Response,
    db: AsyncSession = SessionDep,
):
    """Retorna las categorías de fallas activas."""
    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=60"
    return await mantencion_service.get_categorias(db)


@router.get("/fallas", response_model=List[FallaTallerDTO])
async def get_fallas(
    categoria_id: Optional[int] = Query(None, description="Filtrar por ID de categoría"),
    db: AsyncSession = SessionDep,
):
    """Retorna el catálogo maestro de fallas de taller preconcebidas."""
    return await mantencion_service.get_fallas(db, categoria_id)


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
    2. multipart/form-data: Envío directo del formulario y archivos fotográficos adjuntos ('foto'/'evidencias'),
       subiendo automáticamente al almacenamiento configurado mediante el servicio interno.
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
    return await mantencion_service.create_solicitud(
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
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Pestaña 1 Mecánico: Buses esperando en taller (REPORTADO / PENDIENTE, default: 20 por página)."""
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
    total = await mantencion_service.count_pendientes(db)
    response.headers["X-Total-Count"] = str(total)
    return await mantencion_service.list_pendientes(db, limit=limit, skip=skip)


@router.get("/mis-trabajos", response_model=List[SolicitudResumenDTO])
async def list_mis_trabajos(
    response: Response,
    skip: int = Query(DEFAULT_PAGE_SKIP, ge=0, description="Número de solicitudes a omitir para paginación"),
    limit: Optional[int] = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Límite de solicitudes a retornar (default: 20)"),
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Pestaña 2 Mecánico: Buses asignados activamente al mecánico que realiza la consulta (default: 20 por página)."""
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
    total = await mantencion_service.count_mis_trabajos(db, mecanico_id=current_user.id)
    response.headers["X-Total-Count"] = str(total)
    return await mantencion_service.list_mis_trabajos(db, mecanico_id=current_user.id, limit=limit, skip=skip)



@router.get("/{id}", response_model=SolicitudDTO)
async def get_solicitud(
    id: int,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Obtiene el detalle completo de una solicitud por su ID."""
    logger.debug("[MANTENCION] Consultando solicitud id=%s por usuario_id=%s", id, current_user.id)
    return await mantencion_service.get_solicitud(db, id)


@router.get("/{id}/pauta", response_model=PautaEstadoResumenDTO)
async def get_pauta_solicitud(
    id: int,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Retorna el estado de completitud y respuestas de la pauta preventiva para una solicitud."""
    return await mantencion_service.get_pauta_resumen(db, solicitud_id=id)


@router.post("/{id}/pauta", response_model=PautaEstadoResumenDTO)
async def guardar_respuestas_pauta(
    id: int,
    dto: PautaBatchUpdateDTO,
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Registra o actualiza en lote respuestas a los ítems de la pauta preventiva."""
    logger.info(
        "[MANTENCION] Guardando respuestas de pauta en solicitud_id=%s | mecanico_id=%s | total_respuestas=%s",
        id,
        current_user.id,
        len(dto.respuestas),
    )
    return await mantencion_service.guardar_respuestas_pauta(
        db, solicitud_id=id, dto=dto, mecanico_id=current_user.id
    )


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
    return await mantencion_service.autoasignar_fallas(
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
    return await mantencion_service.asignar_fallas_supervisora(
        db, solicitud_id=id, dto=dto, supervisor_id=current_user.id
    )


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
    return await mantencion_service.cambiar_estado_solicitud(
        db,
        solicitud_id=id,
        dto=dto,
        supervisor_id=current_user.id,
        supervisor_nombre=current_user.nombre_completo,
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
    return await mantencion_service.terminar_avance(
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
    return await mantencion_service.tomar_trabajo(db, solicitud_id=id, mecanico_id=current_user.id, dto=dto)


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
    return await mantencion_service.desasignar_mecanico(
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
    return await mantencion_service.liberar_turno(
        db,
        solicitud_id=id,
        usuario_id=current_user.id,
        dto=dto,
        usuario_nombre=current_user.nombre_completo,
    )


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
    return await mantencion_service.agregar_falla(
        db, solicitud_id=id, mecanico_id=current_user.id, dto=dto
    )


@router.patch("/{id}/detalles/{detalle_id}/check", response_model=DetalleUpdateDTO)
async def check_detalle(
    id: int,
    detalle_id: int,
    resuelto: bool = Query(..., description="True para marcar resuelto, False para desmarcar"),
    current_user: UsuarioResponseDTO = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Marca o desmarca un check de falla resuelta guardando el timestamp y el ID del mecánico."""
    logger.info(
        "[MANTENCION] Check falla en solicitud_id=%s | detalle_id=%s | resuelto=%s | mecanico_id=%s",
        id,
        detalle_id,
        resuelto,
        current_user.id,
    )
    return await mantencion_service.check_detalle(
        db,
        solicitud_id=id,
        detalle_id=detalle_id,
        mecanico_id=current_user.id,
        resuelto=resuelto,
        mecanico_nombre=current_user.nombre_completo,
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
    return await mantencion_service.reportar_repuesto(
        db,
        solicitud_id=id,
        detalle_id=detalle_id,
        dto=dto,
        mecanico_id=current_user.id,
        mecanico_nombre=current_user.nombre_completo,
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
    return await mantencion_service.agregar_colaborador(db, solicitud_id=id, mecanico_id=current_user.id, dto=dto)


@router.post("/{id}/comentarios", response_model=ComentarioAddedDTO)
async def agregar_comentario(
    id: int,
    dto: ComentarioCreateDTO,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Agrega un comentario a la bitácora independiente de la solicitud."""
    logger.info(
        "[MANTENCION] Agregando comentario en solicitud_id=%s | usuario_id=%s",
        id,
        current_user.id,
    )
    return await mantencion_service.agregar_comentario(
        db,
        solicitud_id=id,
        usuario_id=current_user.id,
        dto=dto,
        usuario_nombre=current_user.nombre_completo,
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
    return await mantencion_service.finalizar_solicitud(
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
    return await mantencion_service.liberar_solicitud(
        db,
        solicitud_id=id,
        dto=dto,
        mecanico_id=current_user.id,
        mecanico_nombre=current_user.nombre_completo,
    )
