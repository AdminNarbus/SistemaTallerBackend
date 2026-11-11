from unittest.mock import AsyncMock

from pydantic import SecretStr

from app.core.config import settings
from app.modules.auth.dtos.conductor_sync_dto import ConductorSyncResponseDTO
from app.modules.auth.services.conductor_sync_service import conductor_sync_service


async def test_sync_sin_secreto_rechazado(client, monkeypatch):
    monkeypatch.setattr(settings, "CONDUCTORES_SYNC_SECRET", None)
    response = await client.post("/api/v1/interno/conductores/sincronizar")
    assert response.status_code == 403


async def test_sync_credencial_incorrecta_rechazada(client, monkeypatch):
    monkeypatch.setattr(settings, "CONDUCTORES_SYNC_SECRET", SecretStr("prueba-secreto"))
    response = await client.post("/api/v1/interno/conductores/sincronizar",
                                 headers={"X-Conductores-Sync-Key": "incorrecta"})
    assert response.status_code == 403


async def test_scheduler_sin_origin_pasa_con_secreto(client, monkeypatch):
    monkeypatch.setattr(settings, "CONDUCTORES_SYNC_SECRET", SecretStr("prueba-secreto"))
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", True)
    servicio = AsyncMock(return_value=ConductorSyncResponseDTO(periodo="2026-11", recibidos=410))
    monkeypatch.setattr(conductor_sync_service, "sincronizar", servicio)

    response = await client.post("/api/v1/interno/conductores/sincronizar",
                                 headers={"X-Conductores-Sync-Key": "prueba-secreto"})

    assert response.status_code == 200
    assert response.json()["recibidos"] == 410
    servicio.assert_awaited_once()
