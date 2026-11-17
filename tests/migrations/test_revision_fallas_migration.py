import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_revision_fallas_conserva_historial_y_es_reversible():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/041_revision_fallas.py"
    spec = importlib.util.spec_from_file_location("revision_fallas", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE usuarios (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE taller_solicitudes (id INTEGER PRIMARY KEY, es_ot BOOLEAN NOT NULL)")
        conn.exec_driver_sql("CREATE TABLE taller_solicitud_detalles (id INTEGER PRIMARY KEY, solicitud_id INTEGER NOT NULL)")
        conn.exec_driver_sql("INSERT INTO taller_solicitudes VALUES (1, true), (2, false)")
        conn.exec_driver_sql("INSERT INTO taller_solicitud_detalles VALUES (1, 1), (2, 2)")
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            rows = conn.execute(sa.text("SELECT estado_revision, revisado_por_id, fecha_revision FROM taller_solicitud_detalles ORDER BY id")).all()
            assert rows == [("APROBADA", None, None), ("PENDIENTE", None, None)]
            conn.exec_driver_sql("INSERT INTO taller_solicitud_detalles (id, solicitud_id) VALUES (3, 1)")
            assert conn.scalar(sa.text("SELECT estado_revision FROM taller_solicitud_detalles WHERE id=3")) == "PENDIENTE"
            module.downgrade()
            assert conn.scalar(sa.text("SELECT count(*) FROM taller_solicitud_detalles")) == 3
            module.upgrade()
    engine.dispose()
