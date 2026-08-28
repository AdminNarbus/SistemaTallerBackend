from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.modules.auth.models.usuario import Usuario
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import SolicitudDTO

router = APIRouter(prefix="/supervision", tags=["supervision"])


@router.get("/auditoria/buses-taller", response_model=List[SolicitudDTO])
async def get_auditoria_buses_taller(
    current_user: Usuario = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    """
    Dashboard Auditor para Supervisores/Administradores:
    Retorna la trazabilidad completa en vivo de todos los buses en taller, incluyendo
    historial inmutable de equipos de mecánicos por turno, checks de fallas con marcas de tiempo
    y la bitácora de comentarios cronológica.
    """
    return await mantencion_service.list_auditoria(db)
