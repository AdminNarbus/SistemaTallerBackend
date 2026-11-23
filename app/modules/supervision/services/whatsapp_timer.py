"""Sondea las alertas por tiempo, aunque no haya peticiones al dashboard."""
import asyncio
import logging

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.supervision.services.whatsapp_service import whatsapp_service

logger = logging.getLogger(__name__)


async def ejecutar_timer_whatsapp() -> None:
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await whatsapp_service.notificar(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[WHATSAPP-TIMER] Ciclo fallido; se revisará en el próximo intervalo")
        await asyncio.sleep(settings.WHATSAPP_INTERVAL_SECONDS)
