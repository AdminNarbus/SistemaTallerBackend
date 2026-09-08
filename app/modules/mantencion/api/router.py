from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_current_user,
    require_supervisor_or_admin,
    require_mecanico_or_admin,
    require_conductor_or_admin,
)
from app.modules.auth.models.usuario import Usuario
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import (
    CategoriaFallaDTO,
    FallaTallerDTO,
    SolicitudDTO,
    SolicitudResumenDTO,
    SolicitudCreateDTO,
    TomarTrabajoDTO,
    LiberarTurnoDTO,
    FinalizarSolicitudDTO,
    ComentarioCreateDTO,
    AgregarColaboradorDTO,
    AutoasignarFallasDTO,
    AsignarFallasSupervisoraDTO,
    TerminarAvanceDTO,
    ReportarRepuestoDTO,
    PautaTallerItemDTO,
    PautaEstadoResumenDTO,
    PautaBatchUpdateDTO,
    LiberarSolicitudDTO,
    AgregarFallaDTO,
)

router = APIRouter(prefix="/mantencion", tags=["mantencion"])


@router.get("/pauta/items", response_model=List[PautaTallerItemDTO])
async def get_pauta_items(
    response: Response,
    current_user: Usuario = Depends(require_current_user),
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
    dto: SolicitudCreateDTO,
    current_user: Usuario = Depends(require_conductor_or_admin),
    db: AsyncSession = SessionDep,
):
    return await mantencion_service.create_solicitud(
        db, dto, creador_id=current_user.id, creador_nombre=current_user.nombre_completo
    )


@router.get("/pendientes", response_model=List[SolicitudResumenDTO])
async def list_pendientes(
    response: Response,
    skip: int = Query(0, ge=0, description="Número de solicitudes a omitir para paginación"),
    limit: Optional[int] = Query(50, ge=1, le=100, description="Límite de solicitudes a retornar"),
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Pestaña 1 Mecánico: Buses esperando en taller (REPORTADO / PENDIENTE / PENDIENTE_REASIGNACION)."""
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
    return await mantencion_service.list_pendientes(db, limit=limit, skip=skip)


@router.get("/mis-trabajos", response_model=List[SolicitudResumenDTO])
async def list_mis_trabajos(
    response: Response,
    skip: int = Query(0, ge=0, description="Número de solicitudes a omitir para paginación"),
    limit: Optional[int] = Query(50, ge=1, le=100, description="Límite de solicitudes a retornar"),
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Pestaña 2 Mecánico: Buses asignados activamente al mecánico que realiza la consulta."""
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
    return await mantencion_service.list_mis_trabajos(db, mecanico_id=current_user.id, limit=limit, skip=skip)


@router.get("/{id}", response_model=SolicitudDTO)
async def get_solicitud(
    id: int,
    current_user: Usuario = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Obtiene el detalle completo de una solicitud por su ID."""
    return await mantencion_service.get_solicitud(db, id)


@router.get("/{id}/pauta", response_model=PautaEstadoResumenDTO)
async def get_pauta_solicitud(
    id: int,
    current_user: Usuario = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Retorna el estado de completitud y respuestas de la pauta preventiva para una solicitud."""
    return await mantencion_service.get_pauta_resumen(db, solicitud_id=id)


@router.post("/{id}/pauta", response_model=PautaEstadoResumenDTO)
async def guardar_respuestas_pauta(
    id: int,
    dto: PautaBatchUpdateDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Registra o actualiza en lote respuestas a los ítems de la pauta preventiva."""
    return await mantencion_service.guardar_respuestas_pauta(
        db, solicitud_id=id, dto=dto, mecanico_id=current_user.id
    )


@router.post("/{id}/autoasignar", response_model=SolicitudDTO)
async def autoasignar_fallas(
    id: int,
    dto: AutoasignarFallasDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Autoasignación atómica de fallas por parte de un mecánico.
    Cada mecánico responde únicamente por las fallas específicas que toma.
    Soporta co-responsabilidad: si 2 o más mecánicos toman la misma falla, ambos quedan registrados.
    """
    return await mantencion_service.autoasignar_fallas(
        db, solicitud_id=id, dto=dto, mecanico_id=current_user.id
    )


@router.post("/{id}/asignar", response_model=SolicitudDTO)
async def asignar_fallas_supervisora(
    id: int,
    dto: AsignarFallasSupervisoraDTO,
    current_user: Usuario = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Asignación atómica de fallas realizada por la supervisora o administradores a un mecánico específico.
    Permite co-responsabilidad si la falla ya tenía otro mecánico asignado.
    """
    return await mantencion_service.asignar_fallas_supervisora(
        db, solicitud_id=id, dto=dto, supervisor_id=current_user.id
    )


@router.post("/{id}/terminar-avance", response_model=SolicitudDTO)
async def terminar_avance(
    id: int,
    dto: TerminarAvanceDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Cierra el turno o avance del mecánico en sus fallas asignadas, registrando la duración en minutos.
    Si ya no quedan mecánicos activos en la solicitud, el estado pasa a PENDIENTE.
    """
    return await mantencion_service.terminar_avance(
        db, solicitud_id=id, dto=dto, mecanico_id=current_user.id
    )


@router.post("/{id}/tomar", response_model=SolicitudDTO)
async def tomar_trabajo(
    id: int,
    dto: TomarTrabajoDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Auto-asignación de bus + invitación a colaboradores + comentario inicial opcional."""
    return await mantencion_service.tomar_trabajo(db, solicitud_id=id, mecanico_id=current_user.id, dto=dto)


@router.post("/{id}/desasignarme", response_model=SolicitudDTO)
async def desasignar_mecanico(
    id: int,
    comentario: Optional[str] = Query(None, description="Comentario opcional de salida"),
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Desasignación individual de un mecánico ('[🚪 Salir del Equipo]')."""
    return await mantencion_service.desasignar_mecanico(db, solicitud_id=id, mecanico_id=current_user.id, comentario=comentario)


@router.post("/{id}/liberar-turno", response_model=SolicitudDTO)
async def liberar_turno(
    id: int,
    dto: LiberarTurnoDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Liberación / Entrega de turno para el equipo completo ('[🔄 Entregar / Pasar Turno]')."""
    return await mantencion_service.liberar_turno(db, solicitud_id=id, usuario_id=current_user.id, dto=dto)


@router.post("/{id}/detalles", response_model=SolicitudDTO, status_code=status.HTTP_201_CREATED)
async def agregar_falla(
    id: int,
    dto: AgregarFallaDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Permite a un mecánico o supervisor agregar una nueva avería detectada durante la atención."""
    return await mantencion_service.agregar_falla(
        db, solicitud_id=id, mecanico_id=current_user.id, dto=dto
    )


@router.patch("/{id}/detalles/{detalle_id}/check", response_model=SolicitudDTO)
async def check_detalle(
    id: int,
    detalle_id: int,
    resuelto: bool = Query(..., description="True para marcar resuelto, False para desmarcar"),
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Marca o desmarca un check de falla resuelta guardando el timestamp y el ID del mecánico."""
    return await mantencion_service.check_detalle(
        db, solicitud_id=id, detalle_id=detalle_id, mecanico_id=current_user.id, resuelto=resuelto
    )


@router.patch("/{id}/detalles/{detalle_id}/repuesto", response_model=SolicitudDTO)
async def reportar_repuesto(
    id: int,
    detalle_id: int,
    dto: ReportarRepuestoDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Reporta si una falla no puede continuar por falta de repuestos."""
    return await mantencion_service.reportar_repuesto(
        db,
        solicitud_id=id,
        detalle_id=detalle_id,
        dto=dto,
        mecanico_id=current_user.id,
    )


@router.post("/{id}/agregar-colaborador", response_model=SolicitudDTO)
async def agregar_colaborador(
    id: int,
    dto: AgregarColaboradorDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Agrega un colaborador al equipo mientras la solicitud está EN_REPARACION."""
    return await mantencion_service.agregar_colaborador(db, solicitud_id=id, mecanico_id=current_user.id, dto=dto)


@router.post("/{id}/comentarios", response_model=SolicitudDTO)
async def agregar_comentario(
    id: int,
    dto: ComentarioCreateDTO,
    current_user: Usuario = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Agrega un comentario a la bitácora independiente de la solicitud."""
    return await mantencion_service.agregar_comentario(db, solicitud_id=id, usuario_id=current_user.id, dto=dto)


@router.post("/{id}/finalizar", response_model=SolicitudDTO)
async def finalizar_solicitud(
    id: int,
    dto: FinalizarSolicitudDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Finaliza los trabajos de la solicitud, verifica pauta preventiva y fallas, liberando el bus de taller."""
    return await mantencion_service.finalizar_solicitud(
        db, solicitud_id=id, mecanico_cierre_id=current_user.id, dto=dto
    )


@router.post("/{id}/liberar", response_model=SolicitudDTO)
async def liberar_solicitud(
    id: int,
    dto: LiberarSolicitudDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Cierra y libera el bus de taller. Exige justificación si la pauta está incompleta o si quedan fallas no resueltas."""
    return await mantencion_service.liberar_solicitud(
        db, solicitud_id=id, dto=dto, mecanico_id=current_user.id
    )


