import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.modules.supervision.services import whatsapp_timer as timer


@pytest.mark.parametrize("error", [None, RuntimeError("fallo simulado")])
async def test_timer_cierra_sesion_y_continua_tras_fallo(monkeypatch, error):
    context = AsyncMock()
    notificar = AsyncMock(side_effect=error)
    sleep = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(timer, "AsyncSessionLocal", lambda: context)
    monkeypatch.setattr(timer.whatsapp_service, "notificar", notificar)
    monkeypatch.setattr(timer.asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await timer.ejecutar_timer_whatsapp()

    notificar.assert_awaited_once_with(context.__aenter__.return_value)
    context.__aexit__.assert_awaited_once()
    sleep.assert_awaited_once_with(settings.WHATSAPP_INTERVAL_SECONDS)


@pytest.mark.parametrize("habilitado,timer_habilitado", [(False, True), (True, False), (True, True)])
async def test_lifespan_inicia_y_cancela_timer(monkeypatch, habilitado, timer_habilitado):
    import importlib

    main = importlib.import_module("app.main")
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(settings, "SEED_ON_STARTUP", False)
    monkeypatch.setattr(settings, "REALTIME_ENABLED", False)
    monkeypatch.setattr(settings, "CONDUCTORES_SYNC_TIMER_ENABLED", False)
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", habilitado)
    monkeypatch.setattr(settings, "WHATSAPP_TIMER_ENABLED", timer_habilitado)
    monkeypatch.setattr(main, "engine", AsyncMock())
    eventos = []

    async def ejecutar():
        eventos.append("iniciado")
        try:
            await asyncio.Event().wait()
        finally:
            eventos.append("cancelado")

    monkeypatch.setattr(timer, "ejecutar_timer_whatsapp", ejecutar)
    async with main.lifespan(main.app):
        await asyncio.sleep(0)
        assert eventos == (["iniciado"] if habilitado and timer_habilitado else [])

    assert eventos == (["iniciado", "cancelado"] if habilitado and timer_habilitado else [])
