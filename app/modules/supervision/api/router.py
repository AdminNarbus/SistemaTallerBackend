import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.modules.auth.models.usuario import Usuario
from app.modules.mantencion.dtos.mantencion_dto import SolicitudDTO
from app.modules.supervision.dtos.supervision_dto import ResumenTallerDTO
from app.modules.supervision.services.supervision_service import supervision_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/supervision", tags=["supervision"])


@router.get("/auditoria/buses-taller", response_model=List[SolicitudDTO])
async def get_auditoria_buses_taller(
    n_bus: Optional[str] = Query(None, description="Filtrar por número de bus"),
    estado: Optional[str] = Query(None, description="Filtrar por estado (REPORTADO, EN_REPARACION, PENDIENTE_REASIGNACION, FINALIZADO)"),
    mecanico_id: Optional[int] = Query(None, description="Filtrar por ID de mecánico asignado"),
    current_user: Usuario = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Dashboard Auditor para Supervisores/Administradores:
    Retorna la trazabilidad completa en vivo de todos los buses en taller, incluyendo
    historial inmutable de equipos de mecánicos por turno, checks de fallas con marcas de tiempo
    y la bitácora de comentarios cronológica. Permite filtros por bus, estado y mecánico.
    """
    logger.info("[SUPERVISION] Consulta auditoría buses taller | supervisor_id=%s | n_bus=%s | estado=%s", current_user.id, n_bus, estado)
    result = await supervision_service.get_auditoria_solicitudes(db, n_bus=n_bus, estado=estado, mecanico_id=mecanico_id)
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
    porcentaje global de fallas resueltas, categorización de averías más frecuentes y buses activos.
    """
    logger.info("[SUPERVISION] Consulta resumen y KPIs del taller | supervisor_id=%s", current_user.id)
    resumen = await supervision_service.get_resumen_taller(db)
    return resumen
