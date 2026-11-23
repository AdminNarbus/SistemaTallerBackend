from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.modules.auth.dtos import UsuarioResponseDTO
from app.modules.supervision.dtos.whatsapp_dto import WhatsappEnvioDTO, WhatsappResumenDTO
from app.modules.supervision.services.whatsapp_service import whatsapp_service

router = APIRouter(prefix="/supervision/alertas/whatsapp", tags=["Alertas WhatsApp"])


@router.post("/envios", response_model=WhatsappResumenDTO)
async def notificar_alertas(
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> WhatsappResumenDTO:
    """Envía las alertas vigentes a los números configurados; deduplica reintentos."""
    return await whatsapp_service.notificar(db)


@router.get("/envios", response_model=list[WhatsappEnvioDTO])
async def listar_envios(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> list[WhatsappEnvioDTO]:
    return await whatsapp_service.listar(db, (skip, limit))
