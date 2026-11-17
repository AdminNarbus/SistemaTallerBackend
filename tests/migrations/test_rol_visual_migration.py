import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_visual_migration_upgrade_downgrade_cycle(tmp_path):
    database = tmp_path / "visual.sqlite"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE roles (id INTEGER PRIMARY KEY, nombre VARCHAR(50) UNIQUE, descripcion VARCHAR(255))"
        ))
        connection.execute(text("INSERT INTO roles (nombre) VALUES ('ADMIN')"))

    # Aplicar la revisión real sobre una BD temporal con la tabla existente.
    path = Path(__file__).resolve().parents[2] / "alembic/versions/040_rol_visual.py"
    spec = importlib.util.spec_from_file_location("rol_visual", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
            assert connection.scalar(text("SELECT count(*) FROM roles WHERE nombre='VISUAL'")) == 1
            migration.downgrade()
            assert connection.scalar(text("SELECT count(*) FROM roles WHERE nombre='VISUAL'")) == 0
            migration.upgrade()
            assert connection.scalar(text("SELECT count(*) FROM roles WHERE nombre='ADMIN'")) == 1
    engine.dispose()
