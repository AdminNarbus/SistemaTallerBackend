import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.modules.supervision.models import TelegramEnvio
from app.modules.supervision.dtos.telegram_dto import TelegramResultadoDTO
from app.modules.supervision.services import telegram_scheduler as scheduler_module
from app.modules.supervision.services.telegram_service import telegram_service


@pytest.mark.asyncio
async def test_vencimiento_reinicio_reintento_y_cierre(monkeypatch, tmp_path):
    engine = create_async_engine(f'sqlite+aiosqlite:///{(tmp_path / "telegram.db").as_posix()}')
    async with engine.begin() as conn:
        await conn.execute(text('CREATE TABLE taller_solicitudes (id INTEGER PRIMARY KEY, estado TEXT, n_bus TEXT, fecha_creacion DATETIME, fecha_liberacion DATETIME, fecha_primer_ingreso_taller DATETIME)'))
        await conn.run_sync(TelegramEnvio.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(scheduler_module, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(settings, 'TELEGRAM_ENABLED', True)
    monkeypatch.setattr(settings, 'TELEGRAM_SOLICITUDES_ENABLED', False)
    monkeypatch.setattr(settings, 'TELEGRAM_DESTINATARIOS', '-123')
    monkeypatch.setattr(settings, 'TELEGRAM_SEVERIDAD_MINIMA', 'BAJA')
    intentos = []
    primer_intento = asyncio.Event()

    class Sender:
        async def enviar(self, envio):
            intentos.append(envio.solicitud_id)
            if len(intentos) == 1:
                primer_intento.set()
                return TelegramResultadoDTO(estado='REINTENTABLE', codigo_error='HTTP_429', proximo_intento=datetime.now(timezone.utc) + timedelta(seconds=3))
            return TelegramResultadoDTO(estado='ACEPTADO', telegram_message_id='1')

    monkeypatch.setattr(telegram_service, 'sender', Sender())
    # El redondeo a décimas activa el umbral tres minutos antes de la hora exacta.
    limite = settings.SUPERVISION_UMBRAL_TALLER_HORAS_BAJA
    creada = datetime.now(timezone.utc) - timedelta(hours=limite) + timedelta(minutes=3, seconds=3)
    async with factory() as db:
        await db.execute(text("INSERT INTO taller_solicitudes VALUES (1, 'PENDIENTE', 'PRUEBA', :fecha, NULL, NULL)"), {'fecha': creada.replace(tzinfo=None)})
        await db.commit()

    scheduler = scheduler_module.TelegramScheduler()
    task = asyncio.create_task(scheduler.run())
    await asyncio.wait_for(primer_intento.wait(), timeout=12)
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with factory() as db:
        registros = (await db.scalars(select(TelegramEnvio))).all()
        assert len(registros) == 1
        assert registros[0].estado == 'REINTENTABLE'
        assert registros[0].intentos == 1
    assert intentos == [1]

    # El proceso reiniciado recupera el reintento sin duplicar el envío aceptado.
    scheduler = scheduler_module.TelegramScheduler()
    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(4)
    async with factory() as db:
        registro = (await db.scalars(select(TelegramEnvio))).one()
        assert registro.estado == 'ACEPTADO'
        assert registro.intentos == 2
        fecha_futura = datetime.now(timezone.utc) - timedelta(hours=limite) + timedelta(minutes=3, seconds=4)
        await db.execute(text("UPDATE taller_solicitudes SET estado='FINALIZADO' WHERE id=1"))
        await db.execute(text("INSERT INTO taller_solicitudes VALUES (2, 'PENDIENTE', 'PRUEBA 2', :fecha, NULL, NULL)"), {'fecha': fecha_futura.replace(tzinfo=None)})
        await db.commit()
    scheduler.wake.set()
    await asyncio.sleep(0.5)
    async with factory() as db:
        await db.execute(text("UPDATE taller_solicitudes SET estado='LIBERADO', fecha_liberacion=:fecha WHERE id=2"), {'fecha': datetime.now(timezone.utc).replace(tzinfo=None)})
        await db.commit()
    scheduler.wake.set()
    await asyncio.sleep(5)
    assert intentos == [1, 1]
    async with factory() as db:
        await db.execute(text("UPDATE taller_solicitudes SET estado='FINALIZADO' WHERE id=2"))
        await db.commit()
    scheduler.wake.set()
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert intentos == [1, 1]
    async with factory() as db:
        assert await scheduler.next_deadline(db) is None
        fecha_vencida = datetime.now(timezone.utc) - timedelta(hours=limite, seconds=5)
        await db.execute(text("INSERT INTO taller_solicitudes VALUES (3, 'PENDIENTE', 'PRUEBA 3', :fecha, NULL, NULL)"), {'fecha': fecha_vencida.replace(tzinfo=None)})
        await db.commit()
    # El vencimiento ocurrido con el proceso apagado se recupera al arrancar.
    scheduler = scheduler_module.TelegramScheduler()
    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert intentos == [1, 1, 3]
    await engine.dispose()
