import asyncio
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, create_engine, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test_motivo_salida_estadia import postgres_temporal
from app.core.config import settings
from app.modules.supervision.dtos.supervision_dto import AlertaSupervisionDTO
from app.modules.supervision.dtos.whatsapp_dto import WhatsappResultadoDTO
from app.modules.supervision.models import WhatsappEnvio
from app.modules.supervision.repository.whatsapp_repository import WhatsappRepository
from app.modules.supervision.services.supervision_service import supervision_service
from app.modules.supervision.services.whatsapp_service import WhatsappAlertasService


def cargar_migracion():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/042_whatsapp_envios.py"
    spec = importlib.util.spec_from_file_location("whatsapp_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verificar_ciclo(conn):
    migration = cargar_migracion()
    metadata = MetaData()
    WhatsappEnvio.__table__.to_metadata(metadata)
    with Operations.context(MigrationContext.configure(conn)):
        migration.upgrade()
        migration.downgrade()
        migration.upgrade()
    context = MigrationContext.configure(conn, opts={"compare_type": True, "compare_server_default": True})
    assert compare_metadata(context, metadata) == []


def test_ciclo_sqlite_y_concordancia_modelo():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        verificar_ciclo(conn)
    engine.dispose()


async def test_postgres_migracion_y_concurrencia_real(postgres_temporal, monkeypatch):
    pg = postgres_temporal
    engine = create_async_engine(f"postgresql+asyncpg://migration_test@127.0.0.1:{pg.port}/postgres")
    sesiones = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(settings, "WHATSAPP_DESTINATARIOS", "56911111111")
    monkeypatch.setattr(settings, "WHATSAPP_SEVERIDAD_MINIMA", "BAJA")
    alerta = AlertaSupervisionDTO(
        tipo="LIBERADO_TIEMPO_EXCEDIDO", severidad="CRITICA", solicitud_id=42,
        n_bus="305", mensaje="Liberado con fallas pendientes",
    )
    monkeypatch.setattr(supervision_service, "get_alertas_taller", AsyncMock(return_value=[alerta]))
    sender = AsyncMock()
    sender.enviar.return_value = WhatsappResultadoDTO(estado="ACEPTADO", meta_message_id="wamid.pg")
    service = WhatsappAlertasService(WhatsappRepository(), sender)

    async def ejecutar():
        async with sesiones() as db:
            return await service.notificar(db)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(verificar_ciclo)
        resultados = await asyncio.wait_for(asyncio.gather(ejecutar(), ejecutar()), timeout=20)
        assert sum(r.aceptados for r in resultados) == 1
        assert sum(r.omitidos for r in resultados) == 1
        sender.enviar.assert_awaited_once()

        # La actualización condicional también arbitra los reintentos vencidos.
        alerta.severidad = "ALTA"
        sender.enviar.return_value = WhatsappResultadoDTO(
            estado="REINTENTABLE", codigo_error="HTTP_429",
            proximo_intento=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        assert (await ejecutar()).reintentos_pendientes == 1
        async with sesiones() as db:
            await db.execute(update(WhatsappEnvio).where(WhatsappEnvio.estado == "REINTENTABLE").values(
                proximo_intento=datetime.now(timezone.utc) - timedelta(seconds=1),
            ))
            await db.commit()
        sender.enviar.return_value = WhatsappResultadoDTO(estado="ACEPTADO", meta_message_id="wamid.retry")
        resultados = await asyncio.wait_for(asyncio.gather(ejecutar(), ejecutar()), timeout=20)
        assert sum(r.aceptados for r in resultados) == 1
        assert sum(r.omitidos for r in resultados) == 1
        assert sender.enviar.await_count == 3
    finally:
        await engine.dispose()
