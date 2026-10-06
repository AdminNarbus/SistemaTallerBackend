"""Disposable localhost PostgreSQL validation; leaves the application DB untouched."""
import logging
import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from app.core.config import settings

logger = logging.getLogger(__name__)


def assert_rejected(connection, statement, parameters=None):
    savepoint = connection.begin_nested()
    try:
        connection.execute(text(statement), parameters or {})
    except IntegrityError:
        savepoint.rollback()
    else:
        savepoint.rollback()
        raise AssertionError('PostgreSQL accepted invalid data: ' + statement)


def verify_postgres_rules():
    engine = create_engine(settings.sync_database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        bus = connection.scalar(text("INSERT INTO buses(patente,n_bus) VALUES ('TEST-DB','TEST-DB') RETURNING id"))
        ot = connection.scalar(text("INSERT INTO taller_solicitudes(n_bus,bus_id) VALUES ('TEST-DB',:bus) RETURNING id"), {'bus': bus})
        other = connection.scalar(text("INSERT INTO taller_solicitudes(n_bus) VALUES ('OT-OTHER') RETURNING id"))
        connection.execute(text("INSERT INTO categorias_falla(id,nombre) VALUES (10000,'CAT ORIGINAL')"))
        connection.execute(text("INSERT INTO fallas_taller(id,categoria_id,nombre) VALUES (10000,10000,'FALLA ORIGINAL')"))
        detail = connection.scalar(text("INSERT INTO taller_solicitud_detalles(solicitud_id,falla_id) VALUES (:ot,10000) RETURNING id"), {'ot': ot})
        connection.execute(text("UPDATE fallas_taller SET nombre='RENOMBRADA' WHERE id=10000"))
        assert connection.scalar(text('SELECT falla_nombre_snapshot FROM taller_solicitud_detalles WHERE id=:id'), {'id': detail}) == 'FALLA ORIGINAL'
        assert_rejected(connection, "UPDATE taller_solicitud_detalles SET resuelto=true WHERE id=:id", {'id': detail})
        assert_rejected(connection, "INSERT INTO taller_asignacion_fallas(solicitud_id,detalle_id,mecanico_id) VALUES (:ot,:detail,1)", {'ot': other, 'detail': detail})
        comment = connection.scalar(text("INSERT INTO taller_solicitud_comentarios(solicitud_id,usuario_id,comentario) VALUES (:ot,1,'Registro') RETURNING id"), {'ot': ot})
        assert_rejected(connection, 'DELETE FROM taller_solicitud_comentarios WHERE id=:id', {'id': comment})
        assert_rejected(connection, "UPDATE taller_solicitud_comentarios SET comentario='Alterado' WHERE id=:id", {'id': comment})
        assert_rejected(connection, 'DELETE FROM usuarios WHERE id=1')
        assert_rejected(connection, "INSERT INTO taller_solicitud_evidencias(solicitud_id,detalle_id,url) VALUES (:ot,:detail,'test')", {'ot': other, 'detail': detail})
        assert_rejected(connection, "INSERT INTO reportes_neumaticos(ruedas) VALUES ('[1,2]')")
        assert_rejected(connection, "INSERT INTO buses(patente) VALUES (' test-db ')")
        connection.execute(text('INSERT INTO taller_asignacion_fallas(solicitud_id,detalle_id,mecanico_id) VALUES (:ot,:detail,1)'), {'ot': ot, 'detail': detail})
        assert_rejected(connection, 'INSERT INTO taller_asignacion_fallas(solicitud_id,detalle_id,mecanico_id) VALUES (:ot,:detail,1)', {'ot': ot, 'detail': detail})
        stay = connection.scalar(text("INSERT INTO taller_solicitud_estadias(solicitud_id,numero_visita,fecha_ingreso) VALUES (:ot,1,'2026-09-29 10:00:00+00') RETURNING id"), {'ot': ot})
        assert connection.scalar(text('SELECT en_taller FROM buses WHERE id=:bus'), {'bus': bus}) is True
        assert_rejected(connection, "INSERT INTO taller_solicitud_estadias(solicitud_id,numero_visita,fecha_ingreso) VALUES (:ot,2,now())", {'ot': ot})
        connection.execute(text("UPDATE taller_solicitud_estadias SET fecha_salida='2026-09-29 12:00:00+00' WHERE id=:id"), {'id': stay})
        assert connection.scalar(text('SELECT horas_taller_acumuladas FROM taller_solicitudes WHERE id=:ot'), {'ot': ot}) == 2
        assert connection.scalar(text('SELECT en_taller FROM buses WHERE id=:bus'), {'bus': bus}) is False
        transaction.rollback()
    engine.dispose()


def copy_local_data(source_url):
    """Only SELECT on source; writes go to this script's disposable database."""
    source = create_engine(source_url)
    target = create_engine(settings.sync_database_url)
    if not make_url(settings.sync_database_url).database.startswith('narbus_bd_test_'):
        raise RuntimeError('Data copy destination is not a disposable test database')
    metadata = MetaData()
    metadata.reflect(bind=target)
    tables = [t for t in metadata.sorted_tables if t.name != 'alembic_version']
    with source.connect() as original, target.begin() as destination:
        original.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        names = ','.join('"' + t.name + '"' for t in tables)
        destination.execute(text('TRUNCATE ' + names + ' RESTART IDENTITY CASCADE'))
        for table in tables:
            rows = original.execute(text('SELECT * FROM "' + table.name + '" ORDER BY id')).mappings().all()
            if rows:
                destination.execute(table.insert(), [dict(row) for row in rows])
            if 'id' in table.c:
                destination.execute(text("SELECT setval(pg_get_serial_sequence(:table,'id'),COALESCE((SELECT max(id) FROM " + table.name + "),1), EXISTS (SELECT 1 FROM " + table.name + "))"), {'table': table.name})
    source.dispose()
    target.dispose()


def main():
    original_url = settings.sync_database_url
    url = make_url(original_url)
    if url.host not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeError('Migration tests require localhost')
    name = 'narbus_bd_test_' + uuid.uuid4().hex[:12]
    admin = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        settings.DATABASE_URL = url.set(database=name).render_as_string(hide_password=False)
        config = Config('alembic.ini')
        source_engine = create_engine(original_url)
        with source_engine.connect() as connection:
            source_revision = connection.scalar(text('SELECT version_num FROM alembic_version'))
        source_engine.dispose()
        command.upgrade(config, source_revision)
        copy_local_data(original_url)
        command.upgrade(config, 'head')
        command.check(config)
        verify_postgres_rules()
        from scripts.validar_historial_estados_postgres import validar_historial
        validar_historial(assert_rejected)
        command.downgrade(config, '021_consolidar_ots_activas')
        command.upgrade(config, 'head')
        command.check(config)
        logger.info('Ciclo PostgreSQL upgrade/check/downgrade/upgrade/check aprobado')
    finally:
        settings.DATABASE_URL = original_url
        with admin.connect() as connection:
            # Only this randomly named DB created above may be dropped.
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
