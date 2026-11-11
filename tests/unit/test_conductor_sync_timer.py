import asyncio
from unittest.mock import AsyncMock

import pytest

from app.modules.auth.services import conductor_sync_timer as timer


@pytest.mark.asyncio
async def test_periodo_completado_no_abre_sesion(monkeypatch):
    monkeypatch.setattr(timer, "periodo_pendiente", lambda _: "2026-11")
    session_factory = AsyncMock()
    monkeypatch.setattr(timer, "AsyncSessionLocal", session_factory)
    assert await timer.sincronizar_periodo_pendiente("2026-11") == "2026-11"
    session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_arranque_ejecuta_pendiente_con_sesion_propia(monkeypatch):
    monkeypatch.setattr(timer, "periodo_pendiente", lambda _: "2026-11")
    context = AsyncMock()
    monkeypatch.setattr(timer, "AsyncSessionLocal", lambda: context)
    sync = AsyncMock()
    monkeypatch.setattr(timer.conductor_sync_service, "sincronizar", sync)
    assert await timer.sincronizar_periodo_pendiente(None) == "2026-11"
    sync.assert_awaited_once_with(context.__aenter__.return_value)
    context.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error, espera", [(None, 60), (RuntimeError("fallo"), 300)])
async def test_loop_reintenta_error_y_respeta_cancelacion(monkeypatch, error, espera):
    sync = AsyncMock(return_value="2026-11", side_effect=error)
    sleep = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(timer, "sincronizar_periodo_pendiente", sync)
    monkeypatch.setattr(timer.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await timer.ejecutar_timer_conductores()
    sleep.assert_awaited_once_with(espera)
