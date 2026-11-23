"""Adaptador HTTP de Meta; nunca registra tokens, teléfonos ni cuerpos de error."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

from app.core.config import settings
from app.modules.supervision.dtos.whatsapp_dto import WhatsappNotificacionDTO, WhatsappResultadoDTO

logger = logging.getLogger(__name__)
RETRY_DELAY_SECONDS = 300
MAX_RETRY_DELAY_SECONDS = 86400


class WhatsappSender(Protocol):
    async def enviar(self, envio: WhatsappNotificacionDTO) -> WhatsappResultadoDTO: ...


def construir_payload(envio: WhatsappNotificacionDTO) -> dict:
    es_solicitud = envio.tipo == "SOLICITUD_CHOFER"
    nombre = settings.WHATSAPP_SOLICITUDES_TEMPLATE_NAME if es_solicitud else settings.WHATSAPP_TEMPLATE_NAME
    idioma = settings.WHATSAPP_SOLICITUDES_TEMPLATE_LANGUAGE if es_solicitud else settings.WHATSAPP_TEMPLATE_LANGUAGE
    parametros = envio.parametros
    if es_solicitud and len(parametros) == 3:
        nombre, idioma = "narbus_fallas", "es_CL"
    elif es_solicitud and nombre == "narbus_fallas" and len(parametros) == 4:
        conductor, bus, solicitud, fallas = parametros
        sufijo = f" (informado por {conductor})"
        parametros = [solicitud, bus, fallas[:450-len(sufijo)].rstrip(" .") + sufijo]
    return {
        "messaging_product": "whatsapp", "recipient_type": "individual",
        "to": envio.destinatario, "type": "template",
        "template": {
            "name": nombre,
            "language": {"code": idioma},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "text": texto} for texto in parametros
            ]}],
        },
    }


def interpretar_respuesta(response: httpx.Response) -> WhatsappResultadoDTO:
    if response.status_code == 429:
        espera = response.headers.get("Retry-After", "")
        segundos = RETRY_DELAY_SECONDS
        if espera.isdecimal():
            segundos = min(MAX_RETRY_DELAY_SECONDS, max(RETRY_DELAY_SECONDS, int(espera)))
        return WhatsappResultadoDTO(
            estado="REINTENTABLE", codigo_error="HTTP_429",
            proximo_intento=datetime.now(timezone.utc) + timedelta(seconds=segundos),
        )
    if not response.is_success:
        return WhatsappResultadoDTO(
            estado="FALLIDO" if 400 <= response.status_code < 500 else "INCIERTO",
            codigo_error=f"HTTP_{response.status_code}",
        )
    try:
        message_id = response.json()["messages"][0]["id"]
        if isinstance(message_id, str) and 0 < len(message_id) <= 255:
            return WhatsappResultadoDTO(estado="ACEPTADO", meta_message_id=message_id)
    except (ValueError, KeyError, IndexError, TypeError):
        pass
    return WhatsappResultadoDTO(estado="INCIERTO", codigo_error="RESPUESTA_INVALIDA")


class MetaWhatsappClient:
    async def enviar(self, envio: WhatsappNotificacionDTO) -> WhatsappResultadoDTO:
        """Un timeout puede ocurrir después de aceptar el envío: nunca se reenvía."""
        url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN.get_secret_value()}"}
        try:
            async with httpx.AsyncClient(timeout=settings.WHATSAPP_TIMEOUT_SECONDS) as client:
                response = await client.post(url, headers=headers, json=construir_payload(envio))
            return interpretar_respuesta(response)
        except httpx.RequestError:
            logger.warning("[WHATSAPP] Resultado de red incierto | solicitud_id=%s", envio.solicitud_id)
            return WhatsappResultadoDTO(estado="INCIERTO", codigo_error="ERROR_RED")
