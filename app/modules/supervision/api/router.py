import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.modules.auth.models.usuario import Usuario
from app.modules.mantencion.dtos.mantencion_dto import AsignarFallasSupervisoraDTO, SolicitudDTO
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.supervision.dtos.supervision_dto import ResumenTallerDTO, AlertaSupervisionDTO
from app.modules.supervision.services.supervision_service import supervision_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/supervision", tags=["supervision"])


@router.get("/alertas", response_model=List[AlertaSupervisionDTO])
async def get_alertas_taller(
    current_user: Usuario = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Centro de Alertas de Taller para Supervisores:
    Retorna alertas operacionales activas: fallas detenidas por falta de repuestos,
    ítems de pauta preventiva detectados con defecto, y buses en reparación sin mecánicos activos.
    """
    logger.info("[SUPERVISION] Consulta centro de alertas | supervisor_id=%s", current_user.id)
    return await supervision_service.get_alertas_taller(db)


@router.get("/auditoria/buses-taller", response_model=List[SolicitudDTO])
async def get_auditoria_buses_taller(
    n_bus: Optional[str] = Query(None, description="Filtrar por número de bus"),
    estado: Optional[str] = Query(None, description="Filtrar por estado (REPORTADO, EN_REPARACION, PENDIENTE_REASIGNACION, FINALIZADO)"),
    mecanico_nombre: Optional[str] = Query(None, description="Filtrar por nombre, apellido o username de mecánico asignado o resolutor"),
    current_user: Usuario = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Dashboard Auditor para Supervisores/Administradores:
    Retorna la trazabilidad completa en vivo de todos los buses en taller, incluyendo
    historial inmutable de equipos de mecánicos por turno, checks de fallas con marcas de tiempo
    y la bitácora de comentarios cronológica. Permite filtros por bus, estado y nombre/username del mecánico.
    """
    logger.info("[SUPERVISION] Consulta auditoría buses taller | supervisor_id=%s | n_bus=%s | estado=%s | mecanico_nombre=%s", current_user.id, n_bus, estado, mecanico_nombre)
    result = await supervision_service.get_auditoria_solicitudes(db, n_bus=n_bus, estado=estado, mecanico_nombre=mecanico_nombre)
    logger.debug("[SUPERVISION] Auditoría retornada | total_solicitudes=%s", len(result))
    return result


@router.get("/resumen-taller", response_model=ResumenTallerDTO)
async def get_resumen_taller(
    current_user: Usuario = Depends(require_supervisor_or_admin),
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
    current_user: Usuario = Depends(require_supervisor_or_admin),
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
    return await mantencion_service.asignar_fallas_supervisora(
        db, solicitud_id=id, dto=dto, supervisor_id=current_user.id
    )

