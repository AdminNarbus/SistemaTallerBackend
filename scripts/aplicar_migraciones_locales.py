"""Back up and upgrade the configured localhost DB through Alembic only."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from app.core.config import settings

logger = logging.getLogger(__name__)


def main() -> None:
    url = make_url(settings.sync_database_url)
    if url.host not in ('localhost', '127.0.0.1', '::1') or settings.ENVIRONMENT.value != 'dev_local':
        raise RuntimeError('Este script solo permite la BD local en dev_local')
    engine = create_engine(url)
    backup = {'created_at': datetime.now(timezone.utc).isoformat(), 'tables': {}}
    with engine.connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        for table in inspect(connection).get_table_names():
            quoted = connection.dialect.identifier_preparer.quote(table)
            rows = connection.execute(text('SELECT * FROM ' + quoted)).mappings().all()
            backup['tables'][table] = [dict(row) for row in rows]
    engine.dispose()
    directory = Path('backups')
    directory.mkdir(exist_ok=True)
    path = directory / ('integridad_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    path.write_text(json.dumps(backup, default=str, ensure_ascii=False), encoding='utf-8')
    logger.info('Respaldo de datos guardado: %s | tablas=%s', path, len(backup['tables']))
    config = Config('alembic.ini')
    command.upgrade(config, 'head')
    command.check(config)
    logger.info('BD local migrada y alineada con los modelos')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
