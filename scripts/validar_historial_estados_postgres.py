"""Casos de historial ejecutados únicamente en la BD desechable del validador."""
import asyncio
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from scripts.importar_historial_estados_ot import importar


def validar_historial(assert_rejected):
    url = make_url(settings.sync_database_url)
    if url.host not in ('localhost', '127.0.0.1', '::1') or not url.database.startswith('narbus_bd_test_'):
        raise RuntimeError('La validación del historial requiere una BD local desechable')
    engine = create_engine(settings.sync_database_url)
    with engine.begin() as connection:
        ot = connection.scalar(text("INSERT INTO taller_solicitudes(n_bus) VALUES ('HIST-PG') RETURNING id"))
        other = connection.scalar(text("INSERT INTO taller_solicitudes(n_bus) VALUES ('HIST-PG-OTHER') RETURNING id"))
        parametros = {'ot': ot, 'other': other}
        comment = connection.scalar(text("INSERT INTO taller_solicitud_comentarios(solicitud_id,usuario_id,tipo,comentario) VALUES (:ot,1,'CAMBIO_ESTADO','Supervisora Ana cambió el estado de FINALIZADO a PENDIENTE.') RETURNING id"), parametros)
        parametros['comment'] = comment
        connection.execute(text("INSERT INTO taller_solicitud_comentarios(solicitud_id,usuario_id,tipo,comentario) VALUES (:ot,1,'CIERRE','Pedro finalizó los trabajos de la OT y liberó el bus para operaciones.')"), parametros)
        insert = "INSERT INTO taller_solicitud_estado_eventos(solicitud_id,tipo_evento,estado_anterior,estado_nuevo,actor_nombre_snapshot,origen,comentario_id) VALUES (:ot,'CAMBIO_ESTADO','PENDIENTE','FINALIZADO','Ana','OPERACION',:comment)"
        assert_rejected(connection, insert, {**parametros, 'ot': other})
        assert_rejected(connection, insert, {**parametros, 'ot': -1, 'comment': None})
        assert_rejected(connection, insert.replace("'FINALIZADO'", "'PENDIENTE'"), parametros)
        assert_rejected(connection, insert.replace("'FINALIZADO'", "'DESCONOCIDO'"), parametros)
        assert_rejected(connection, insert.replace("'CAMBIO_ESTADO'", "'CIERRE_HISTORICO'"), parametros)
        assert_rejected(connection, insert.replace("'Ana'", "' '"), parametros)
        assert_rejected(connection, insert.replace("'OPERACION'", "'BITACORA'"), {**parametros, 'comment': None})
        event_id = connection.scalar(text(insert + ' RETURNING id'), {**parametros, 'comment': None})
        assert_rejected(connection, 'UPDATE taller_solicitud_estado_eventos SET motivo=\'Cambio\' WHERE id=:id', {'id': event_id})
        assert_rejected(connection, 'DELETE FROM taller_solicitud_estado_eventos WHERE id=:id', {'id': event_id})
        assert_rejected(connection, 'DELETE FROM taller_solicitudes WHERE id=:ot', parametros)
        assert_rejected(connection, insert.replace('actor_nombre_snapshot,', 'usuario_actor_id,actor_nombre_snapshot,').replace("'Ana'", "-1,'Ana'"), parametros)

    with engine.connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION READ ONLY')
        before = connection.scalar(text('SELECT count(*) FROM taller_solicitud_estado_eventos'))
        simulation = importar(connection, batch_size=1)
        assert simulation['candidatos'] >= 2 and simulation['ambiguos'] >= 1
        assert connection.scalar(text('SELECT count(*) FROM taller_solicitud_estado_eventos')) == before
    with engine.connect() as connection:
        applied = importar(connection, aplicar=True, batch_size=1)
        assert applied['importados'] == simulation['candidatos']
        repeated = importar(connection, aplicar=True, batch_size=1)
        assert repeated['importados'] == 0
        assert repeated['ya_existentes'] >= applied['importados']
        imported = connection.execute(text('SELECT * FROM taller_solicitud_estado_eventos WHERE comentario_id=:comment'), parametros).mappings().one()
        assert imported['estado_anterior'] == 'FINALIZADO' and imported['estado_nuevo'] == 'PENDIENTE'
        assert_rejected(connection, insert, parametros)
        assert connection.scalar(text("SELECT count(*) FROM taller_solicitud_estado_eventos WHERE solicitud_id=:ot AND tipo_evento='CIERRE_HISTORICO' AND estado_nuevo IS NULL"), parametros) == 1
    engine.dispose()
    asyncio.run(validar_operaciones())


async def validar_operaciones():
    from app.modules.taller.dtos import CambiarEstadoSolicitudDTO, FinalizarSolicitudDTO
    from app.modules.taller.services.cierre_service import CierreService

    engine = create_async_engine(settings.async_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    servicio = CierreService()
    try:
        async with sessions() as db:
            id_ot = await db.scalar(text("INSERT INTO taller_solicitudes(n_bus) VALUES ('HIST-PG-FLUJO') RETURNING id"))
            await db.commit()
            for estado in ('FINALIZADO', 'PENDIENTE', 'FINALIZADO'):
                await servicio.cambiar_estado_solicitud(db, id_ot, CambiarEstadoSolicitudDTO(estado=estado), 1, 'Ana')
            eventos = (await db.execute(text('SELECT estado_anterior,estado_nuevo FROM taller_solicitud_estado_eventos WHERE solicitud_id=:ot ORDER BY fecha_evento,id'), {'ot': id_ot})).all()
            assert eventos == [('PENDIENTE', 'FINALIZADO'), ('FINALIZADO', 'PENDIENTE'), ('PENDIENTE', 'FINALIZADO')]
            await db.rollback()

        async def cambiar(estado):
            async with sessions() as db:
                await servicio.cambiar_estado_solicitud(db, id_ot, CambiarEstadoSolicitudDTO(estado=estado), 1, 'Ana')

        # Dos sesiones independientes: cada una debe leer el estado ya serializado.
        await asyncio.wait_for(asyncio.gather(cambiar('EN_REPARACION'), cambiar('PENDIENTE')), timeout=20)
        async with sessions() as db:
            eventos = (await db.execute(text('SELECT estado_anterior,estado_nuevo FROM taller_solicitud_estado_eventos WHERE solicitud_id=:ot ORDER BY fecha_evento,id'), {'ot': id_ot})).all()
            assert len(eventos) == 5
            assert all(previous.estado_nuevo == following.estado_anterior for previous, following in zip(eventos, eventos[1:]))
            current = await db.scalar(text('SELECT estado FROM taller_solicitudes WHERE id=:ot'), {'ot': id_ot})
            assert current == eventos[-1].estado_nuevo
            await db.rollback()
            # Fallo antes de commit: ni el comentario ni la transición sobreviven.
            with patch.object(db, 'commit', side_effect=RuntimeError('Fallo simulado')):
                try:
                    await servicio.cambiar_estado_solicitud(db, id_ot, CambiarEstadoSolicitudDTO(estado='LIBERADO'), 1, 'Ana')
                except RuntimeError:
                    await db.rollback()
                else:
                    raise AssertionError('No se produjo el fallo de commit')
            assert await db.scalar(text('SELECT estado FROM taller_solicitudes WHERE id=:ot'), {'ot': id_ot}) == current
            assert await db.scalar(text('SELECT count(*) FROM taller_solicitud_estado_eventos WHERE solicitud_id=:ot'), {'ot': id_ot}) == 5
            # Cierre batch real con triggers de estadía y telemetría instalados.
            await servicio.finalizar_solicitud(db, id_ot, 1, FinalizarSolicitudDTO(), 'Ana')
            assert await db.scalar(text('SELECT estado FROM taller_solicitudes WHERE id=:ot'), {'ot': id_ot}) == 'FINALIZADO'
            count = await db.scalar(text('SELECT count(*) FROM taller_solicitud_estado_eventos WHERE solicitud_id=:ot'), {'ot': id_ot})
            await servicio.finalizar_solicitud(db, id_ot, 1, FinalizarSolicitudDTO(), 'Ana')
            assert await db.scalar(text('SELECT count(*) FROM taller_solicitud_estado_eventos WHERE solicitud_id=:ot'), {'ot': id_ot}) == count
    finally:
        await engine.dispose()
