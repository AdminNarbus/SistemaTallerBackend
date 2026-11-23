from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, settings
from app.core.exceptions import BusinessRuleException
from app.modules.supervision.dtos.supervision_dto import AlertaSupervisionDTO
from app.modules.supervision.dtos.whatsapp_dto import WhatsappResultadoDTO
from app.modules.supervision.repository.whatsapp_repository import WhatsappRepository
from app.modules.supervision.services.supervision_service import supervision_service
from app.modules.supervision.services.whatsapp_client import MetaWhatsappClient, interpretar_respuesta
from app.modules.supervision.services.whatsapp_service import WhatsappAlertasService, construir_notificacion


def alerta(**cambios):
    return AlertaSupervisionDTO(**({
        "tipo": "OT_SIN_INGRESO_TALLER", "severidad": "ALTA", "solicitud_id": 42,
        "n_bus": "305", "mensaje": "Bus 305 sin ingreso por 216 horas", "horas_acumuladas": 216,
    } | cambios))


@pytest.fixture
def whatsapp_config(monkeypatch):
    config = {
        "WHATSAPP_ENABLED": True, "WHATSAPP_ACCESS_TOKEN": SecretStr("test-token"),
        "WHATSAPP_PHONE_NUMBER_ID": "123456", "WHATSAPP_API_VERSION": "v23.0",
        "WHATSAPP_DESTINATARIOS": "56911111111", "WHATSAPP_SEVERIDAD_MINIMA": "BAJA",
        "WHATSAPP_TEMPLATE_NAME": "alerta_taller", "WHATSAPP_TEMPLATE_LANGUAGE": "es",
    }
    for key, value in config.items():
        monkeypatch.setattr(settings, key, value)
    return config


@pytest.mark.parametrize("numero", [
    "123", "056911111111", "569ABC11111", "56911111111;56922222222", "+" + "1" * 16, "5１２３４５６７８",
])
def test_config_rechaza_numeros_invalidos(numero):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, WHATSAPP_DESTINATARIOS=numero)


def test_config_normaliza_destinatarios_y_exige_credenciales():
    config = Settings(_env_file=None, WHATSAPP_DESTINATARIOS=" +56911111111,56911111111, 56922222222 ")
    assert config.WHATSAPP_DESTINATARIOS == "56911111111,56922222222"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, WHATSAPP_ENABLED=True)


def test_clave_estable_ignora_horas_y_fecha_pero_distingue_severidad_y_numero():
    original = construir_notificacion(alerta(), "56911111111")
    actualizado = construir_notificacion(alerta(mensaje="Otra duración", horas_acumuladas=220), "56911111111")

    assert original.clave == actualizado.clave
    assert original.clave != construir_notificacion(alerta(severidad="CRITICA"), "56911111111").clave
    assert original.clave != construir_notificacion(alerta(), "56922222222").clave


async def test_cliente_envia_plantilla_a_meta(whatsapp_config, monkeypatch):
    solicitudes = []

    def responder(request):
        solicitudes.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.test"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    monkeypatch.setattr("app.modules.supervision.services.whatsapp_client.httpx.AsyncClient", lambda **kw: client)
    envio = construir_notificacion(alerta(mensaje="Línea\ncon\t espacios"), "56911111111")

    resultado = await MetaWhatsappClient().enviar(envio)

    import json
    request = solicitudes[0]
    payload = json.loads(request.content)
    assert str(request.url) == "https://graph.facebook.com/v23.0/123456/messages"
    assert request.headers["Authorization"] == "Bearer test-token"
    assert payload["to"] == "56911111111"
    assert payload["type"] == "template"
    assert payload["template"]["language"] == {"code": "es"}
    assert [p["text"] for p in payload["template"]["components"][0]["parameters"]] == [
        "ALTA", "OT_SIN_INGRESO_TALLER", "305", "42", "Línea con espacios",
    ]
    assert resultado.estado == "ACEPTADO"
    assert resultado.meta_message_id == "wamid.test"


async def test_timeout_es_incierto_sin_reintento(whatsapp_config, monkeypatch, caplog):
    def responder(request):
        raise httpx.ReadTimeout("secreto que nunca debe registrarse", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    monkeypatch.setattr("app.modules.supervision.services.whatsapp_client.httpx.AsyncClient", lambda **kw: client)

    resultado = await MetaWhatsappClient().enviar(construir_notificacion(alerta(), "56911111111"))

    assert resultado.estado == "INCIERTO"
    assert "secreto" not in caplog.text
    assert "56911111111" not in caplog.text


@pytest.mark.parametrize("status,body,esperado", [
    (400, {"error": {"message": "privado"}}, "FALLIDO"),
    (401, {}, "FALLIDO"), (500, {}, "INCIERTO"), (503, {}, "INCIERTO"),
    (200, {}, "INCIERTO"), (200, {"messages": []}, "INCIERTO"),
    (200, {"messages": [{"id": 23}]}, "INCIERTO"),
    (200, {"messages": [{"id": "wamid.1"}]}, "ACEPTADO"),
])
def test_clasificacion_respuesta(status, body, esperado):
    resultado = interpretar_respuesta(httpx.Response(status, json=body))
    assert resultado.estado == esperado
    assert "privado" not in resultado.model_dump_json()


def test_429_respeta_retry_after():
    antes = datetime.now(timezone.utc)
    resultado = interpretar_respuesta(httpx.Response(429, headers={"Retry-After": "600"}))
    assert resultado.estado == "REINTENTABLE"
    assert resultado.proximo_intento >= antes + timedelta(seconds=600)


async def test_servicio_confirma_reserva_antes_de_enviar_y_filtra(whatsapp_config, monkeypatch):
    repo = AsyncMock(spec=WhatsappRepository)
    repo.reservar.return_value = (1, 1)
    db = AsyncMock()
    sender = AsyncMock()

    async def enviar(notificacion):
        assert db.commit.await_count == 3
        return WhatsappResultadoDTO(estado="ACEPTADO", meta_message_id="wamid.1")

    sender.enviar.side_effect = enviar
    monkeypatch.setattr(settings, "WHATSAPP_SEVERIDAD_MINIMA", "ALTA")
    monkeypatch.setattr(supervision_service, "get_alertas_taller", AsyncMock(return_value=[alerta(), alerta(severidad="BAJA")]))

    resumen = await WhatsappAlertasService(repo, sender).notificar(db)

    assert resumen.aceptados == 1
    assert resumen.alertas_activas == 2
    sender.enviar.assert_awaited_once()
    assert db.commit.await_count == 4


async def test_desactivado_no_consulta_ni_envia(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", False)
    repo, sender, db = AsyncMock(spec=WhatsappRepository), AsyncMock(), AsyncMock()

    with pytest.raises(BusinessRuleException):
        await WhatsappAlertasService(repo, sender).notificar(db)

    repo.reservar.assert_not_awaited()
    sender.enviar.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_sin_alertas_no_envia(whatsapp_config, monkeypatch):
    repo, sender, db = AsyncMock(spec=WhatsappRepository), AsyncMock(), AsyncMock()
    monkeypatch.setattr(supervision_service, "get_alertas_taller", AsyncMock(return_value=[]))

    resultado = await WhatsappAlertasService(repo, sender).notificar(db)

    assert resultado.alertas_activas == 0
    repo.reservar.assert_not_awaited()
    sender.enviar.assert_not_awaited()
