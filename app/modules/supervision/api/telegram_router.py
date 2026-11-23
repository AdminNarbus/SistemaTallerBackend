from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.modules.auth.dtos import UsuarioResponseDTO
from app.modules.supervision.dtos.telegram_dto import TelegramEnvioDTO, TelegramResumenDTO
from app.modules.supervision.services.telegram_service import telegram_service

router = APIRouter(prefix="/supervision/alertas/telegram", tags=["Alertas Telegram"])


@router.post("/envios", response_model=TelegramResumenDTO)
async def notificar_alertas(
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> TelegramResumenDTO:
    """Envía las alertas vigentes a los números configurados; deduplica reintentos."""
    return await telegram_service.notificar(db)


@router.get("/envios", response_model=list[TelegramEnvioDTO])
async def listar_envios(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> list[TelegramEnvioDTO]:
    return await telegram_service.listar(db, (skip, limit))
