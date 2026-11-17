"""Temporizador mensual ligado al ciclo de vida del backend."""
import asyncio
import logging
from datetime import datetime

from app.core.database import AsyncSessionLocal
from app.modules.auth.services.conductor_sync_service import (
    CHILE_TIMEZONE,
    conductor_sync_service,
    periodo_pendiente,
)

logger = logging.getLogger(__name__)
CHECK_INTERVAL_SECONDS = 60
ERROR_RETRY_SECONDS = 300


async def sincronizar_periodo_pendiente(ultimo_periodo: str | None) -> str:
    periodo = periodo_pendiente(datetime.now(CHILE_TIMEZONE))
    if periodo == ultimo_periodo:
        return periodo
    async with AsyncSessionLocal() as session:
        await conductor_sync_service.sincronizar(session)
    return periodo


async def ejecutar_timer_conductores() -> None:
    """Recupera el último período vencido al arrancar y reintenta tras errores.

    El servicio existente aplica lock transaccional y deduplicación persistente
    por mes para coordinar múltiples procesos e instancias.
    """
    ultimo_periodo = None
    while True:
        intervalo = CHECK_INTERVAL_SECONDS
        try:
            ultimo_periodo = await sincronizar_periodo_pendiente(ultimo_periodo)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("[CONDUCTOR-TIMER] Intento fallido; se reintentará en %s segundos", ERROR_RETRY_SECONDS)
            intervalo = ERROR_RETRY_SECONDS
        await asyncio.sleep(intervalo)
