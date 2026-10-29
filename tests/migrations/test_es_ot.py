import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

from test_motivo_salida_estadia import postgres_temporal


def sql_migracion(direccion):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/033_es_ot_distinguir_solicitudes_y_ordenes.py"
    spec = importlib.util.spec_from_file_location("migracion_es_ot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    salida = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": salida})
    with Operations.context(context):
        getattr(module, direccion)()
    return salida.getvalue()


def test_es_ot_preserva_registros_previos_y_nuevos_nacen_solicitud(postgres_temporal):
    pg = postgres_temporal
    pg.sql("""CREATE TABLE taller_solicitudes (id int PRIMARY KEY, estado varchar(50));
        INSERT INTO taller_solicitudes VALUES (1, 'PENDIENTE'), (2, 'FINALIZADO');""")
    pg.sql(sql_migracion("upgrade"))
    assert pg.sql("SELECT count(*) FROM taller_solicitudes WHERE es_ot = true") == "2"
    pg.sql("INSERT INTO taller_solicitudes(id, estado) VALUES (3, 'PENDIENTE')")
    assert pg.sql("SELECT es_ot FROM taller_solicitudes WHERE id = 3") == "f"
    pg.sql(sql_migracion("downgrade"))
    assert pg.sql("SELECT count(*) FROM taller_solicitudes") == "3"
    assert pg.sql("SELECT count(*) FROM information_schema.columns WHERE table_name='taller_solicitudes' AND column_name='es_ot'") == "0"
    pg.sql(sql_migracion("upgrade"))
    pg.sql("INSERT INTO taller_solicitudes(id, estado) VALUES (4, 'PENDIENTE')")
    assert pg.sql("SELECT es_ot FROM taller_solicitudes WHERE id = 4") == "f"
