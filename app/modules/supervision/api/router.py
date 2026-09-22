import logging
from typing import List, Optional
from fastapi import APIRouter, Body, Depends, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.auth.services.auth_service import auth_service
from app.modules.buses.dtos import BusCreateDTO, BusDarDeBajaDTO, BusResponseDTO
from app.modules.buses.services.bus_service import bus_service
from app.modules.mantencion.dtos.mantencion_dto import (
    AsignarFallasSupervisoraDTO,
    CambiarEstadoSolicitudDTO,
    SolicitudDTO,
    AgregarFallaDTO,
    ResolverFallaSupervisoraDTO,
    DetalleUpdateDTO,
)
from app.modules.supervision.constants import (
    DEFAULT_PAGE_SKIP,
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    ESTADOS_VALIDOS_AUDITORIA,
)
from app.modules.supervision.dtos import (
    ResumenTallerDTO,
    AlertaSupervisionDTO,
    MecanicoCargaDTO,
    SolicitudAuditoriaDTO,
)
from app.modules.supervision.services import supervision_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/supervision", tags=["supervision"])


@router.get("/alertas", response_model=List[AlertaSupervisionDTO])
async def get_alertas_taller(
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Centro de Alertas de Taller para Supervisores:
    Retorna alertas operacionales activas: buses estancados en taller, buses liberados en ruta
    con fallas pendientes prolongadas, defectos de pauta y buses sin mecánicos asignados.
    """
    logger.info("[SUPERVISION] Consulta centro de alertas | supervisor_id=%s", current_user.id)
    return await supervision_service.get_alertas_taller(db)


@router.get(
    "/mecanicos/carga",
    response_model=List[MecanicoCargaDTO],
    summary="Carga de trabajo y disponibilidad de mecánicos",
    description="Retorna la lista de mecánicos activos junto al conteo de fallas activas asignadas para balancear la carga de trabajo en la supervisión.",
)
async def get_mecanicos_con_carga(
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> List[MecanicoCargaDTO]:
    """Consulta la carga de fallas activas de cada mecánico para apoyar la asignación en taller."""
    logger.info("[SUPERVISION] Consulta carga de mecánicos | supervisor_id=%s", current_user.id)
    return await supervision_service.get_mecanicos_con_carga(db)


@router.get(
    "/usuarios",
    response_model=List[UsuarioResponseDTO],
    summary="Listado paginado de usuarios para Supervisores",
    description="Retorna el listado de usuarios con soporte de paginación (default: 20 por página) y filtros opcionales. Expone X-Total-Count en cabecera.",
)
async def listar_usuarios_supervision(
    response: Response,
    skip: int = Query(DEFAULT_PAGE_SKIP, ge=0, description="Número de usuarios a omitir para paginación"),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Número máximo de usuarios por página (default: 20)"),
    rol: Optional[str] = Query(None, description="Filtrar por nombre de rol (ADMIN, SUPERVISOR, MECANICO, CONDUCTOR)"),
    q: Optional[str] = Query(None, description="Búsqueda por texto en nombre, apellido o username"),
    is_active: Optional[bool] = Query(None, description="Filtrar por estado activo/inactivo"),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> List[UsuarioResponseDTO]:
    """
    Vista del Supervisor para gestión y auditoría del personal:
    Permite consultar los usuarios del sistema de forma paginada (20 por página por defecto),
    con filtros por rol, término de búsqueda y estado activo.
    """
    total = await auth_service.contar_usuarios(db, rol=rol, q=q, is_active=is_active)
    response.headers["X-Total-Count"] = str(total)
    logger.info(
        "[SUPERVISION] Consulta listado de usuarios | supervisor_id=%s | skip=%s | limit=%s | total=%s",
        current_user.id,
        skip,
        limit,
        total,
    )
    return await auth_service.listar_usuarios(
        db, skip=skip, limit=limit, rol=rol, q=q, is_active=is_active
    )


@router.get("/auditoria/buses-taller", response_model=List[SolicitudAuditoriaDTO])
async def get_auditoria_buses_taller(
    response: Response,
    n_bus: Optional[str] = Query(None, description="Filtrar por número de bus"),
    estado: Optional[str] = Query(
        None,
        description=f"Filtrar por estado ({', '.join(ESTADOS_VALIDOS_AUDITORIA)})",
    ),
    mecanico_nombre: Optional[str] = Query(None, description="Filtrar por nombre, apellido o username de mecánico asignado o resolutor"),
    skip: int = Query(DEFAULT_PAGE_SKIP, ge=0, description="Número de registros a omitir para paginación"),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Límite máximo de solicitudes a retornar (default: 20)"),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Dashboard Auditor para Supervisores/Administradores:
    Retorna la trazabilidad completa en vivo de todos los buses en taller, incluyendo
    historial inmutable de equipos de mecánicos por turno, checks de fallas con marcas de tiempo
    y la bitácora de comentarios cronológica. Permite filtros por bus, estado, nombre/username del mecánico y paginación (default: 20 OTs).
    """
    total = await supervision_service.count_auditoria_solicitudes(
        db, n_bus=n_bus, estado=estado, mecanico_nombre=mecanico_nombre
    )
    response.headers["X-Total-Count"] = str(total)
    logger.info(
        "[SUPERVISION] Consulta auditoría buses taller | supervisor_id=%s | n_bus=%s | estado=%s | mecanico_nombre=%s | skip=%s | limit=%s | total=%s",
        current_user.id,
        n_bus,
        estado,
        mecanico_nombre,
        skip,
        limit,
        total,
    )
    result = await supervision_service.get_auditoria_solicitudes(
        db, n_bus=n_bus, estado=estado, mecanico_nombre=mecanico_nombre, skip=skip, limit=limit
    )
    logger.debug("[SUPERVISION] Auditoría retornada | total_solicitudes=%s", len(result))
    return result


@router.get("/resumen-taller", response_model=ResumenTallerDTO)
async def get_resumen_taller(
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Resumen General y KPIs del Taller para Supervisores:
    Retorna indicadores clave de rendimiento (KPIs), desglose por estados,
    porcentaje global de fallas resueltas, categorización de averías más frecuentes,
    conteo físico de buses en taller y alertas operacionales activas.
    """
    logger.info("[SUPERVISION] Consulta resumen y KPIs del taller | supervisor_id=%s", current_user.id)
    resumen = await supervision_service.get_resumen_taller(db)
    return resumen



@router.post("/solicitudes/{id}/asignar", response_model=SolicitudDTO)
async def asignar_fallas_supervisora(
    id: int,
    dto: AsignarFallasSupervisoraDTO,
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Asignación directa de fallas por parte de la supervisora a un mecánico específico.
    Permite co-responsabilidad si la falla ya tenía asignación previa.
    """
    logger.info(
        "[SUPERVISION] Supervisora %s asignando fallas a mecanico_id=%s en solicitud_id=%s",
        current_user.id,
        dto.mecanico_id,
        id,
    )
    return await supervision_service.asignar_fallas_supervisora(
        db, solicitud_id=id, dto=dto, supervisor_id=current_user.id
    )


@router.patch("/solicitudes/{id}/estado", response_model=SolicitudDTO)
async def cambiar_estado_solicitud(
    id: int,
    dto: CambiarEstadoSolicitudDTO,
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Cambio de estado administrativo de una Orden de Trabajo (OT) por parte de la supervisora o administradores.
    Permite transicionar la OT registrando un comentario justificativo en la bitácora inmutable.
    """
    logger.info(
        "[SUPERVISION] Supervisora %s cambiando estado de solicitud_id=%s a %s",
        current_user.id,
        id,
        dto.estado,
    )
    return await supervision_service.cambiar_estado_solicitud(
        db,
        solicitud_id=id,
        dto=dto,
        supervisor_id=current_user.id,
        supervisor_nombre=current_user.nombre_completo,
    )


@router.post(
    "/buses",
    response_model=BusResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar nuevo bus desde panel de supervisión",
    description="Permite a la supervisora o administradores dar de alta un nuevo bus en el sistema.",
)
async def crear_bus_supervision(
    payload: BusCreateDTO = Body(...),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> BusResponseDTO:
    logger.info(
        "[SUPERVISION] Supervisora %s registrando nuevo bus patente='%s', n_bus='%s'",
        current_user.id,
        payload.patente,
        payload.n_bus,
    )
    return await bus_service.create_bus(db, dto=payload, usuario_id=current_user.id)


@router.patch(
    "/buses/{bus_id}/dar-de-baja",
    response_model=BusResponseDTO,
    summary="Dar de baja a un bus desde panel de supervisión",
    description="Permite a la supervisora desactivar un bus de la flota registrando marcas de tiempo y motivo.",
)
async def dar_de_baja_bus_supervision(
    bus_id: int = Path(..., description="ID numérico del bus", ge=1),
    payload: BusDarDeBajaDTO = Body(default_factory=BusDarDeBajaDTO),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> BusResponseDTO:
    logger.info(
        "[SUPERVISION] Supervisora %s dando de baja bus_id=%s | motivo='%s'",
        current_user.id,
        bus_id,
        payload.motivo,
    )
    return await bus_service.dar_de_baja_bus(
        db, bus_id=bus_id, dto=payload, usuario_id=current_user.id
    )


@router.get(
    "/solicitudes/{id}",
    response_model=SolicitudDTO,
    summary="Detalle completo de una OT para Supervisión",
    description="Permite a la supervisora consultar la totalidad de la información de una orden de trabajo (averías, mecánicos asignados, evidencias, bitácora).",
)
async def get_solicitud_supervision(
    id: int = Path(..., description="ID numérico de la solicitud/OT", ge=1),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> SolicitudDTO:
    """Obtiene el detalle completo de una solicitud por su ID desde el panel de supervisión."""
    logger.info("[SUPERVISION] Consulta detalle solicitud_id=%s | supervisor_id=%s", id, current_user.id)
    return await supervision_service.get_solicitud(db, solicitud_id=id)


@router.post(
    "/solicitudes/{id}/detalles",
    response_model=SolicitudDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir falla a una OT desde el panel de supervisión",
    description="Permite a la supervisora agregar una avería a una OT existente, con opción de dejarla pendiente, asignarla de inmediato a un mecánico o registrarla como ya resuelta.",
)
async def agregar_falla_supervision(
    id: int = Path(..., description="ID numérico de la solicitud/OT", ge=1),
    dto: AgregarFallaDTO = Body(...),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> SolicitudDTO:
    """Añade una avería a la orden de trabajo directamente desde la vista de detalle de la OT."""
    logger.info(
        "[SUPERVISION] Supervisora %s agregando falla a solicitud_id=%s | falla_id=%s | resuelto=%s | mecanico_resolvio_id=%s",
        current_user.id,
        id,
        dto.falla_id,
        dto.resuelto,
        dto.mecanico_resolvio_id,
    )
    return await supervision_service.agregar_falla(
        db,
        solicitud_id=id,
        dto=dto,
        supervisor_id=current_user.id,
    )


@router.patch(
    "/solicitudes/{id}/detalles/{detalle_id}/resolver",
    response_model=DetalleUpdateDTO,
    summary="Registrar resolución de avería indicando qué mecánico la reparó",
    description="Permite a la supervisora marcar una falla como resuelta especificando explícitamente el mecánico que la arregló, o reabrirla, registrando el evento en la bitácora inmutable.",
)
@router.patch(
    "/solicitudes/{id}/detalles/{detalle_id}/check",
    response_model=DetalleUpdateDTO,
    summary="Alias de resolución de avería para supervisión",
    description="Alias compatible con /check para marcar o desmarcar resolución indicando el mecánico que arregló la avería.",
)
async def resolver_falla_supervision(
    id: int = Path(..., description="ID numérico de la solicitud/OT", ge=1),
    detalle_id: int = Path(..., description="ID numérico del detalle de falla", ge=1),
    dto: Optional[ResolverFallaSupervisoraDTO] = Body(None),
    resuelto: Optional[bool] = Query(None, description="Parámetro query opcional para resuelto"),
    mecanico_id: Optional[int] = Query(None, description="Parámetro query opcional para mecánico resolutor"),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> DetalleUpdateDTO:
    """Registra qué mecánico arregló una falla puntual desde la vista de detalle de la OT."""
    final_dto = dto or ResolverFallaSupervisoraDTO()
    if resuelto is not None and dto is None:
        final_dto.resuelto = resuelto
    if mecanico_id is not None and not final_dto.effective_mecanico_id:
        final_dto.mecanico_id = mecanico_id

    logger.info(
        "[SUPERVISION] Supervisora %s registrando resolución de falla detalle_id=%s en solicitud_id=%s | resuelto=%s | mecanico_id=%s",
        current_user.id,
        detalle_id,
        id,
        final_dto.resuelto,
        final_dto.effective_mecanico_id,
    )
    return await supervision_service.resolver_falla(
        db,
        solicitud_id=id,
        detalle_id=detalle_id,
        dto=final_dto,
        supervisor_id=current_user.id,
        supervisor_nombre=current_user.nombre_completo,
    )


