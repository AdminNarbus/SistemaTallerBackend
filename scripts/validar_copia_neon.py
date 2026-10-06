"""Lecturas en Neon; migraciones y pruebas exclusivamente en una copia localhost.

NEON_DATABASE_URL puede suministrarse por entorno. El fallback lee la constante
del script legado mediante AST, sin ejecutar su código de mantenimiento.
La copia local se conserva incluso cuando una prueba falla.
"""
import ast
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from scripts.validar_migraciones_postgres import assert_rejected, verify_postgres_rules

logger = logging.getLogger(__name__)


def source_url():
    raw = os.getenv('NEON_DATABASE_URL')
    if not raw:
        module = ast.parse(Path('scripts/eliminar_ot_especifica_neon.py').read_text(encoding='utf-8'))
        raw = next(ast.literal_eval(node.value) for node in module.body
                   if isinstance(node, ast.Assign) and any(
                       isinstance(target, ast.Name) and target.id == 'NEON_URL' for target in node.targets))
    url = make_url(raw).set(drivername='postgresql+psycopg2', query={'sslmode': 'require'})
    if url.database != 'taller' or not url.host.endswith('.neon.tech'):
        raise RuntimeError('El origen debe ser taller en Neon')
    return url


def backup_source(url):
    engine = create_engine(url, connect_args={'connect_timeout': 15})
    backup = {'created_at': datetime.now(timezone.utc).isoformat(), 'source_database': 'taller', 'tables': {}}
    with engine.connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        for name in inspect(connection).get_table_names(schema='public'):
            quoted = connection.dialect.identifier_preparer.quote(name)
            backup['tables'][name] = [dict(row) for row in connection.execute(text('SELECT * FROM public.' + quoted)).mappings()]
    engine.dispose()
    if not backup['tables'].get('alembic_version'):
        raise RuntimeError('El respaldo no incluye la revisión Alembic; no se admite una copia incompleta')
    path = Path('backups') / ('neon_taller_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(backup, default=str, ensure_ascii=False), encoding='utf-8')
    logger.info('Respaldo de datos: %s | tablas=%s | filas=%s', path, len(backup['tables']), sum(map(len, backup['tables'].values())))
    return backup


def verify_preserved_originals(backup):
    engine = create_engine(settings.sync_database_url)
    with engine.connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION READ ONLY')
        for archive in connection.execute(text('SELECT * FROM taller_consolidacion_archivos')).mappings():
            original = next(row for row in backup['tables'][archive['tabla']] if row['id'] == archive['registro_id'])
            encoded = json.loads(json.dumps(original, default=str))
            archived = archive['datos_originales']
            for key, expected in encoded.items():
                actual = archived[key]
                if isinstance(original[key], Decimal):
                    assert Decimal(str(actual)) == original[key], (archive['tabla'], archive['registro_id'], key)
                    continue
                if isinstance(expected, str) and isinstance(actual, str):
                    try:
                        assert datetime.fromisoformat(actual) == datetime.fromisoformat(expected)
                        continue
                    except ValueError:
                        pass
                assert actual == expected, (archive['tabla'], archive['registro_id'], key)
        # All preexisting rows remain operational or have their complete original archived.
        for name, originals in backup['tables'].items():
            if name == 'alembic_version':
                continue
            quoted = connection.dialect.identifier_preparer.quote(name)
            current = set(connection.execute(text('SELECT id FROM ' + quoted)).scalars())
            archived = set(connection.execute(text('SELECT registro_id FROM taller_consolidacion_archivos WHERE tabla=:table'), {'table': name}).scalars())
            assert {row['id'] for row in originals} <= current | archived, name
    engine.dispose()


def restore_backup(backup):
    """Restore exactly the captured snapshot, rather than reread a live source."""
    url = make_url(settings.sync_database_url)
    if url.host not in ('localhost','127.0.0.1','::1') or not url.database.startswith('narbus_bd_test_neon_'):
        raise RuntimeError('Restauración permitida solo en copia local de pruebas')
    engine = create_engine(url)
    metadata = MetaData()
    metadata.reflect(bind=engine)
    tables = [table for table in metadata.sorted_tables if table.name != 'alembic_version']
    with engine.begin() as connection:
        quoted_names = ','.join(connection.dialect.identifier_preparer.quote(table.name) for table in tables)
        connection.execute(text('TRUNCATE ' + quoted_names + ' RESTART IDENTITY CASCADE'))
        for table in tables:
            rows = backup['tables'][table.name]
            quoted = connection.dialect.identifier_preparer.quote(table.name)
            if rows:
                assert set(rows[0]) == set(table.c.keys()), table.name
                connection.execute(text(f'INSERT INTO {quoted} SELECT * FROM json_populate_recordset(NULL::{quoted},CAST(:rows AS json))'),
                                   {'rows':json.dumps(rows,default=str,ensure_ascii=False)})
            assert connection.scalar(text('SELECT count(*) FROM ' + quoted)) == len(rows)
            connection.execute(text("SELECT setval(pg_get_serial_sequence(:table,'id'),COALESCE((SELECT max(id) FROM " + quoted + "),1),EXISTS(SELECT 1 FROM " + quoted + "))"), {'table':table.name})
    engine.dispose()


def main():
    local = make_url(settings.sync_database_url)
    if local.host not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeError('El destino de pruebas debe ser localhost')
    source = source_url()
    backup = backup_source(source)
    revision = backup['tables']['alembic_version'][0]['version_num']
    name = 'narbus_bd_test_neon_' + uuid.uuid4().hex[:10]
    admin = create_engine(local.set(database='postgres'), isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    settings.DATABASE_URL = local.set(database=name).render_as_string(hide_password=False)
    logger.info('Copia local conservada: %s | origen revision=%s', name, revision)
    config = Config('alembic.ini')
    command.upgrade(config, revision)
    restore_backup(backup)
    command.upgrade(config, 'head')
    command.check(config)
    verify_preserved_originals(backup)
    from scripts.verificar_integridad_bd import main as audit
    audit()
    # Existing regression helpers use actor #1. Neon need not have that user:
    # create a clearly synthetic fixture only inside this disposable local copy.
    fixture_engine = create_engine(settings.sync_database_url)
    assert make_url(settings.sync_database_url).database == name
    with fixture_engine.begin() as connection:
        connection.execute(text('''INSERT INTO usuarios(id,username,password_hash,rol_id)
            SELECT 1,:username,'fixture-sin-login',min(id) FROM roles
            HAVING NOT EXISTS (SELECT 1 FROM usuarios WHERE id=1)'''),
            {'username': 'prueba_copia_neon_' + uuid.uuid4().hex})
    fixture_engine.dispose()
    verify_postgres_rules()
    from scripts.validar_historial_estados_postgres import validar_historial
    validar_historial(assert_rejected)
    engine = create_engine(settings.sync_database_url)
    with engine.connect() as connection:
        assert_rejected(connection, 'DELETE FROM taller_consolidacion_archivos')
        assert_rejected(connection, "UPDATE taller_consolidacion_archivos SET tabla='alterada'")
    engine.dispose()
    command.downgrade(config, '021_consolidar_ots_activas')
    command.upgrade(config, 'head')
    command.check(config)
    verify_preserved_originals(backup)
    logging.getLogger('alembic.runtime.migration').info('Copia Neon %s: restauración, migraciones, preservación, integridad y servicios aprobados', name)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
