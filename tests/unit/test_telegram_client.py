import httpx
import pytest
from pydantic import SecretStr

from app.modules.supervision.dtos.telegram_dto import TelegramNotificacionDTO
from app.modules.supervision.services.telegram_client import TelegramClient, construir_mensaje


def ejemplo():
    return TelegramNotificacionDTO(clave="a", solicitud_id=1, tipo="SOLICITUD_CHOFER", severidad="INFO", destinatario="-100123", mensaje="", parametros=["Ana", "B12", "1", "Frenos"])


def test_mensaje_solicitud():
    texto = construir_mensaje(ejemplo())
    assert all(dato in texto for dato in ("Ana", "B12", "Frenos"))


@pytest.mark.asyncio
async def test_envio_aceptado(monkeypatch):
    from app.modules.supervision.services import telegram_client
    monkeypatch.setattr(telegram_client.settings, "TELEGRAM_BOT_TOKEN", SecretStr("token"))
    async def post(self, url, **kwargs):
        assert kwargs["json"]["chat_id"] == "-100123"
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    resultado = await TelegramClient().enviar(ejemplo())
    assert resultado.estado == "ACEPTADO"
    assert resultado.telegram_message_id == "42"
