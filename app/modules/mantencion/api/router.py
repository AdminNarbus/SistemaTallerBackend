from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
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
    SolicitudCreateDTO,
    TomarTrabajoDTO,
    LiberarTurnoDTO,
    FinalizarSolicitudDTO,
    ComentarioCreateDTO,
    AgregarColaboradorDTO,
    AutoasignarFallasDTO,
    AsignarFallasSupervisoraDTO,
    TerminarAvanceDTO,
)
from app.core.exceptions import NotFoundException

router = APIRouter(prefix="/mantencion", tags=["mantencion"])


@router.get("/categorias", response_model=List[CategoriaFallaDTO])
async def get_categorias(db: AsyncSession = SessionDep):
    """Retorna las categorías de fallas activas."""
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
    """Creación de reporte/solicitud de taller por chofer (CONDUCTOR o ADMIN)."""
    return await mantencion_service.create_solicitud(db, dto, creador_id=current_user.id)


@router.get("/pendientes", response_model=List[SolicitudDTO])
async def list_pendientes(
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Pestaña 1 Mecánico: Buses esperando en taller (REPORTADO / PENDIENTE / PENDIENTE_REASIGNACION)."""
    return await mantencion_service.list_pendientes(db)


@router.get("/mis-trabajos", response_model=List[SolicitudDTO])
async def list_mis_trabajos(
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Pestaña 2 Mecánico: Buses asignados activamente al mecánico que realiza la consulta."""
    return await mantencion_service.list_mis_trabajos(db, mecanico_id=current_user.id)


@router.get("/{id}", response_model=SolicitudDTO)
async def get_solicitud(
    id: int,
    current_user: Usuario = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Obtiene el detalle completo de una solicitud por su ID."""
    solicitud = await mantencion_service.get_solicitud(db, id)
    if not solicitud:
        raise NotFoundException("Solicitud de taller no encontrada")
    return solicitud


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
    """Auto-asignación de bus como Líder + invitación a colaboradores + comentario inicial opcional."""
    return await mantencion_service.tomar_trabajo(db, solicitud_id=id, lider_id=current_user.id, dto=dto)


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


@router.post("/{id}/agregar-colaborador", response_model=SolicitudDTO)
async def agregar_colaborador(
    id: int,
    dto: AgregarColaboradorDTO,
    current_user: Usuario = Depends(require_mecanico_or_admin),
    db: AsyncSession = SessionDep,
):
    """Agrega un colaborador al equipo mientras la solicitud está EN_REPARACION. Solo el líder activo puede hacerlo."""
    return await mantencion_service.agregar_colaborador(db, solicitud_id=id, lider_id=current_user.id, dto=dto)


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
    """Finaliza los trabajos de la solicitud y deja el bus en estado DISPONIBLE."""
    return await mantencion_service.finalizar_solicitud(
        db, solicitud_id=id, mecanico_cierre_id=current_user.id, dto=dto
    )

