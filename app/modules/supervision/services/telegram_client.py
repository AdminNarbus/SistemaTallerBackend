"""Envío a Telegram; el token nunca se incluye en los registros."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

from app.core.config import settings
from app.modules.supervision.dtos.telegram_dto import TelegramNotificacionDTO, TelegramResultadoDTO

logger = logging.getLogger(__name__)


class TelegramSender(Protocol):
    async def enviar(self, envio: TelegramNotificacionDTO) -> TelegramResultadoDTO: ...


def construir_mensaje(envio: TelegramNotificacionDTO) -> str:
    if envio.tipo == "SOLICITUD_CHOFER":
        chofer, bus, solicitud, fallas = envio.parametros
        return f"🚌 Nueva solicitud de chofer\n\n👤 Chofer: {chofer}\n🚌 Bus: {bus}\n📋 Solicitud: {solicitud}\n\n🔧 Fallas informadas: {fallas}\n\nRevisa el detalle en el sistema de taller."
    severidad, tipo, bus, solicitud, detalle = envio.parametros
    return f"🚨 Alerta de taller\n\n⚠️ Severidad: {severidad}\n📌 Tipo: {tipo}\n🚌 Bus: {bus}\n📋 Solicitud: {solicitud}\n\n📝 {detalle}"


class TelegramClient:
    async def enviar(self, envio: TelegramNotificacionDTO) -> TelegramResultadoDTO:
        token = settings.TELEGRAM_BOT_TOKEN.get_secret_value()
        try:
            async with httpx.AsyncClient(timeout=settings.TELEGRAM_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": envio.destinatario, "text": construir_mensaje(envio)},
                )
            if response.status_code == 429:
                try:
                    delay = max(1, min(86400, int(response.json().get("parameters", {}).get("retry_after", 300))))
                except (ValueError, TypeError):
                    delay = 300
                return TelegramResultadoDTO(estado="REINTENTABLE", codigo_error="HTTP_429", proximo_intento=datetime.now(timezone.utc) + timedelta(seconds=delay))
            if not response.is_success:
                return TelegramResultadoDTO(estado="FALLIDO" if 400 <= response.status_code < 500 else "INCIERTO", codigo_error=f"HTTP_{response.status_code}")
            data = response.json()
            message_id = data.get("result", {}).get("message_id")
            if data.get("ok") is True and isinstance(message_id, int):
                return TelegramResultadoDTO(estado="ACEPTADO", telegram_message_id=str(message_id))
        except (httpx.RequestError, ValueError):
            logger.warning("[TELEGRAM] Resultado de envío incierto")
        return TelegramResultadoDTO(estado="INCIERTO", codigo_error="RESPUESTA_INCIERTA")
