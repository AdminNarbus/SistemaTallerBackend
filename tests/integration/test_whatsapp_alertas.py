import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.modules.supervision.dtos.supervision_dto import AlertaSupervisionDTO
from app.modules.supervision.dtos.whatsapp_dto import WhatsappResultadoDTO
from app.modules.supervision.models import WhatsappEnvio
from app.modules.supervision.repository.whatsapp_repository import WhatsappRepository
from app.modules.supervision.services.supervision_service import supervision_service
from app.modules.supervision.services.whatsapp_service import WhatsappAlertasService


@pytest.fixture
async def contexto(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_DESTINATARIOS", "56911111111,56922222222")
    monkeypatch.setattr(settings, "WHATSAPP_SEVERIDAD_MINIMA", "BAJA")
    alertas = [AlertaSupervisionDTO(
        tipo="OT_SIN_INGRESO_TALLER", severidad="ALTA", solicitud_id=42,
        n_bus="305", mensaje="Sin ingreso al taller", horas_acumuladas=216,
    )]
    monkeypatch.setattr(supervision_service, "get_alertas_taller", AsyncMock(return_value=alertas))
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'whatsapp.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(WhatsappEnvio.__table__.create)
    sender = AsyncMock()
    sender.enviar.return_value = WhatsappResultadoDTO(estado="ACEPTADO", meta_message_id="wamid.1")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory, WhatsappAlertasService(WhatsappRepository(), sender), sender, alertas
    await engine.dispose()


async def test_deduplicacion_durable_por_destinatario_y_escalamiento(contexto):
    sesiones, service, sender, alertas = contexto

    async with sesiones() as db:
        assert (await service.notificar(db)).aceptados == 2
    # Una sesión y servicio nuevos simulan el siguiente proceso/ciclo.
    async with sesiones() as db:
        assert (await WhatsappAlertasService(WhatsappRepository(), sender).notificar(db)).omitidos == 2
    alertas[0].severidad = "CRITICA"
    async with sesiones() as db:
        assert (await service.notificar(db)).aceptados == 2
        historial = await service.listar(db, (0, 2))

    assert sender.enviar.await_count == 4
    assert len(historial) == 2
    assert all(envio.severidad == "CRITICA" for envio in historial)


async def test_dos_workers_no_envian_dos_veces(contexto):
    sesiones, service, sender, _ = contexto

    async def ejecutar():
        async with sesiones() as db:
            return await service.notificar(db)

    resultados = await asyncio.gather(ejecutar(), ejecutar())

    assert sum(r.aceptados for r in resultados) == 2
    assert sum(r.omitidos for r in resultados) == 2
    assert sender.enviar.await_count == 2


async def test_429_espera_y_limita_tres_intentos(contexto):
    sesiones, service, sender, _ = contexto
    sender.enviar.return_value = WhatsappResultadoDTO(
        estado="REINTENTABLE", codigo_error="HTTP_429",
        proximo_intento=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    async with sesiones() as db:
        assert (await service.notificar(db)).reintentos_pendientes == 2
        assert (await service.notificar(db)).omitidos == 2
        for intento in (2, 3):
            await db.execute(update(WhatsappEnvio).values(proximo_intento=datetime.now(timezone.utc) - timedelta(seconds=1)))
            await db.commit()
            resumen = await service.notificar(db)
            assert getattr(resumen, "reintentos_pendientes" if intento == 2 else "fallidos") == 2
        assert (await service.notificar(db)).omitidos == 2
        registros = list((await db.scalars(select(WhatsappEnvio))).all())

    assert sender.enviar.await_count == 6
    assert all(r.intentos == 3 and r.estado == "FALLIDO" for r in registros)


async def test_incierto_no_se_reenvia_y_fallo_no_impide_otro_destinatario(contexto):
    sesiones, service, sender, _ = contexto
    sender.enviar.side_effect = [
        WhatsappResultadoDTO(estado="INCIERTO", codigo_error="ERROR_RED"),
        WhatsappResultadoDTO(estado="ACEPTADO", meta_message_id="wamid.2"),
    ]

    async with sesiones() as db:
        resumen = await service.notificar(db)
        assert (resumen.inciertos, resumen.aceptados) == (1, 1)
        assert (await service.notificar(db)).omitidos == 2

    assert sender.enviar.await_count == 2


async def test_crash_deja_reserva_durable_y_expira_sin_reenviar(contexto):
    sesiones, service, sender, _ = contexto
    sender.enviar.side_effect = RuntimeError("Caída simulada luego de reservar")

    async with sesiones() as db:
        with pytest.raises(RuntimeError):
            await service.notificar(db)
    sender.enviar.side_effect = None
    async with sesiones() as db:
        await db.execute(update(WhatsappEnvio).values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=11)))
        await db.commit()
        resumen = await service.notificar(db)
        registros = list((await db.scalars(select(WhatsappEnvio).order_by(WhatsappEnvio.id))).all())

    assert (resumen.omitidos, resumen.aceptados) == (1, 1)
    assert registros[0].estado == "INCIERTO"
    assert registros[0].codigo_error == "RESERVA_EXPIRADA"


async def test_endpoint_protegido_y_desactivado(client, auth_headers_supervisor, auth_headers_conductor, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", False)
    path = "/api/v1/supervision/alertas/whatsapp/envios"

    assert (await client.post(path)).status_code == 401
    assert (await client.post(path, headers=auth_headers_conductor)).status_code == 403
    assert (await client.post(path, headers=auth_headers_supervisor)).status_code == 422
    assert (await client.get(path, headers=auth_headers_supervisor)).json() == []
    assert (await client.get(path + "?limit=101", headers=auth_headers_supervisor)).status_code == 422


async def test_endpoint_notifica_y_expone_historial(client, auth_headers_supervisor, monkeypatch):
    from app.modules.supervision.services.whatsapp_service import whatsapp_service

    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_DESTINATARIOS", "56911111111")
    monkeypatch.setattr(settings, "WHATSAPP_SEVERIDAD_MINIMA", "BAJA")
    alertas = [AlertaSupervisionDTO(
        tipo="LIBERADO_TIEMPO_EXCEDIDO", severidad="CRITICA", solicitud_id=42,
        n_bus="305", mensaje="Fallas pendientes en ruta",
    )]
    monkeypatch.setattr(supervision_service, "get_alertas_taller", AsyncMock(return_value=alertas))
    sender = AsyncMock()
    sender.enviar.return_value = WhatsappResultadoDTO(estado="ACEPTADO", meta_message_id="wamid.api")
    monkeypatch.setattr(whatsapp_service, "sender", sender)
    path = "/api/v1/supervision/alertas/whatsapp/envios"

    enviado = await client.post(path, headers=auth_headers_supervisor)
    repetido = await client.post(path, headers=auth_headers_supervisor)
    historial = await client.get(path, headers=auth_headers_supervisor)

    assert enviado.status_code == 200
    assert enviado.json()["aceptados"] == 1
    assert repetido.json()["omitidos"] == 1
    assert historial.json()[0]["meta_message_id"] == "wamid.api"
    assert "mensaje" not in historial.json()[0]
    sender.enviar.assert_awaited_once()


@pytest.mark.parametrize("rol,status", [("ADMIN", 200), ("VISUAL", 403), ("MECANICO", 403)])
async def test_roles_endpoint_manual(client, monkeypatch, rol, status):
    from types import SimpleNamespace
    from app.api.deps import require_current_user
    from app.main import app
    from app.modules.supervision.dtos.whatsapp_dto import WhatsappResumenDTO
    from app.modules.supervision.services.whatsapp_service import whatsapp_service

    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(id=1, rol=rol)
    notificar = AsyncMock(return_value=WhatsappResumenDTO())
    monkeypatch.setattr(whatsapp_service, "notificar", notificar)

    response = await client.post("/api/v1/supervision/alertas/whatsapp/envios")

    assert response.status_code == status
    assert notificar.await_count == (1 if status == 200 else 0)
