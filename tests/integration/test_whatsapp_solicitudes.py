from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.config import settings
from app.modules.supervision.dtos.whatsapp_dto import WhatsappNotificacionDTO, WhatsappResultadoDTO
from app.modules.supervision.models import WhatsappEnvio
from app.modules.supervision.services.whatsapp_client import construir_payload
from app.modules.taller.services.whatsapp_solicitud_service import WhatsappSolicitudesService


def test_plantilla_visual_y_compatibilidad_cola_anterior(monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_SOLICITUDES_TEMPLATE_NAME", "narbus_reporte_fallas_visual")
    envio = WhatsappNotificacionDTO(clave="x", solicitud_id=42, tipo="SOLICITUD_CHOFER", severidad="INFO",
                                    destinatario="56911111111", mensaje="", parametros=["Juan", "305", "42", "Frenos"])
    plantilla = construir_payload(envio)["template"]
    assert plantilla["name"] == "narbus_reporte_fallas_visual"
    assert [p["text"] for p in plantilla["components"][0]["parameters"]] == ["Juan", "305", "42", "Frenos"]
    envio.parametros = ["42", "305", "Frenos (informado por Juan)"]
    plantilla = construir_payload(envio)["template"]
    assert plantilla["name"] == "narbus_fallas"
    assert plantilla["language"]["code"] == "es_CL"
    assert [p["text"] for p in plantilla["components"][0]["parameters"]] == envio.parametros
    envio.parametros = ["Juan", "305", "42", "Frenos"]
    monkeypatch.setattr(settings, "WHATSAPP_SOLICITUDES_TEMPLATE_NAME", "narbus_fallas")
    plantilla = construir_payload(envio)["template"]
    assert [p["text"] for p in plantilla["components"][0]["parameters"]] == ["42", "305", "Frenos (informado por Juan)"]


async def test_reporte_chofer_encola_y_despacha_por_destinatario(
    client, db_session, auth_headers_conductor, monkeypatch,
):
    monkeypatch.setattr(settings, "WHATSAPP_SOLICITUDES_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_SOLICITUDES_DESTINATARIOS", "56911111111,56922222222")
    payload = {"n_bus": "PRUEBA-WA", "descripcion_general": "Revisar motor"}

    response = await client.post("/api/v1/taller/solicitudes", json=payload, headers=auth_headers_conductor)

    assert response.status_code == 201
    registros = list((await db_session.scalars(select(WhatsappEnvio))).all())
    assert len(registros) == 2
    assert all(item.tipo == "SOLICITUD_CHOFER" and item.estado == "PENDIENTE" for item in registros)
    sender = AsyncMock()
    sender.enviar.return_value = WhatsappResultadoDTO(estado="ACEPTADO", meta_message_id="wamid.test")
    service = WhatsappSolicitudesService(sender)
    assert await service.procesar(db_session)
    assert await service.procesar(db_session)
    assert not await service.procesar(db_session)
    assert sender.enviar.await_count == 2
    enviado = sender.enviar.await_args_list[0].args[0]
    assert enviado.parametros[1] == "PRUEBA-WA"
    assert enviado.parametros[0]
    assert enviado.parametros[2] == str(response.json()["id"])
    assert enviado.parametros[3] == "Revisar motor"


async def test_nuevo_reporte_anexado_a_orden_existente_genera_otro_aviso(
    client, db_session, auth_headers_conductor, monkeypatch,
):
    monkeypatch.setattr(settings, "WHATSAPP_SOLICITUDES_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_SOLICITUDES_DESTINATARIOS", "56911111111")
    payload = {"n_bus": "PRUEBA-REPORTE", "descripcion_general": "Revisar motor"}
    primero = await client.post("/api/v1/taller/solicitudes", json=payload, headers=auth_headers_conductor)
    segundo = await client.post("/api/v1/taller/solicitudes", json=payload, headers=auth_headers_conductor)
    assert primero.status_code == segundo.status_code == 201
    assert primero.json()["id"] == segundo.json()["id"]
    registros = list((await db_session.scalars(select(WhatsappEnvio))).all())
    assert len(registros) == 2
    assert registros[0].clave != registros[1].clave


async def test_reportes_de_otros_roles_no_se_encolan(client, db_session, auth_headers_supervisor, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_SOLICITUDES_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_SOLICITUDES_DESTINATARIOS", "56911111111")
    response = await client.post(
        "/api/v1/taller/solicitudes", json={"n_bus": "PRUEBA-ROL"}, headers=auth_headers_supervisor,
    )
    assert response.status_code == 201
    assert (await db_session.scalars(select(WhatsappEnvio))).all() == []
