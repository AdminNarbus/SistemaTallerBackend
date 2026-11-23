import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import MetaData, create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test_motivo_salida_estadia import postgres_temporal
from app.modules.supervision.dtos.whatsapp_dto import WhatsappResultadoDTO
from app.modules.supervision.models import WhatsappEnvio
from app.modules.taller.services.whatsapp_solicitud_service import WhatsappSolicitudesService


def migracion(nombre):
    path = Path(__file__).resolve().parents[2] / 'alembic' / 'versions' / nombre
    spec = importlib.util.spec_from_file_location('migration_' + nombre[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_migracion_y_workers_postgres(postgres_temporal):
    pg = postgres_temporal
    engine = create_engine(f'postgresql://migration_test@127.0.0.1:{pg.port}/postgres')
    m42 = migracion('042_whatsapp_envios.py')
    m43 = migracion('043_whatsapp_solicitudes.py')
    metadata = MetaData()
    WhatsappEnvio.__table__.to_metadata(metadata)
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            m42.upgrade()
            m43.upgrade()
            m43.downgrade()
            m43.upgrade()
        assert compare_metadata(MigrationContext.configure(conn, opts={'compare_server_default': True}), metadata) == []
    engine.dispose()

    async_engine = create_async_engine(f'postgresql+asyncpg://migration_test@127.0.0.1:{pg.port}/postgres')
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    sender = AsyncMock()
    sender.enviar.return_value = WhatsappResultadoDTO(estado='ACEPTADO', meta_message_id='wamid.pg')
    service = WhatsappSolicitudesService(sender)
    try:
        async with factory() as db:
            db.add(WhatsappEnvio(clave='a'*64, solicitud_id=42, tipo='SOLICITUD_CHOFER',
                severidad='INFO', destinatario='56911111111', mensaje='["42","305","Reporte"]',
                estado='PENDIENTE', intentos=1))
            await db.commit()

        async def ejecutar():
            async with factory() as db:
                return await service.procesar(db)

        resultados = await asyncio.wait_for(asyncio.gather(ejecutar(), ejecutar()), timeout=20)
        assert sorted(resultados) == [False, True]
        sender.enviar.assert_awaited_once()
        async with factory() as db:
            registro = await db.scalar(select(WhatsappEnvio))
            assert registro.estado == 'ACEPTADO'
    finally:
        await async_engine.dispose()
