import importlib.util
import io
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from test_motivo_salida_estadia import postgres_temporal


def migration_sql(direction):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/034_pauta_multiples_mecanicos.py"
    spec = importlib.util.spec_from_file_location("pauta_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        getattr(migration, direction)()
    return output.getvalue()


def test_migracion_revisores_backfill_sql_detalle_y_reversion(postgres_temporal):
    pg = postgres_temporal
    pg.sql("""
        CREATE TABLE usuarios(id integer PRIMARY KEY, nombre text, apellido text);
        CREATE TABLE taller_solicitud_pauta(id integer PRIMARY KEY, solicitud_id integer,
            item_id integer, estado text, observacion text, mecanico_id integer REFERENCES usuarios(id),
            fecha_registro timestamptz DEFAULT now());
        CREATE TABLE pauta_taller_items(id integer PRIMARY KEY, categoria text, item text, orden integer);
        INSERT INTO usuarios VALUES (2, 'Pedro', 'Mecanico'), (3, 'Carlos', 'Mecanico');
        INSERT INTO pauta_taller_items VALUES (1, 'General', 'Punto 1', 1);
        INSERT INTO taller_solicitud_pauta(id, solicitud_id, item_id, estado, mecanico_id)
            VALUES (1, 35, 1, 'OK', 2), (2, 36, 1, 'OK', NULL);
    """)
    pg.sql(migration_sql("upgrade"))
    assert pg.sql("SELECT pauta_id, mecanico_id FROM taller_solicitud_pauta_mecanicos") == "1|2"
    pg.sql("INSERT INTO taller_solicitud_pauta_mecanicos VALUES (1, 3)")
    # Ejecutar el CTE real del detalle PostgreSQL: no solo probar el fallback SQLite.
    repo = Path(__file__).resolve().parents[2] / "app/modules/taller/repository/taller_repository.py"
    source = repo.read_text(encoding="utf-8")
    cte = source.split("pauta_agg AS (", 1)[1].split("\n                SELECT", 1)[0]
    result = pg.sql("WITH filtered_solicitud AS (SELECT 35 AS id), pauta_agg AS (" + cte +
                    " SELECT pauta_json->0->'mecanicos' FROM pauta_agg")
    import json
    assert [m["id"] for m in json.loads(result)] == [2, 3]
    with pytest.raises(AssertionError):
        pg.sql(migration_sql("downgrade"))
    assert pg.sql("SELECT count(*) FROM taller_solicitud_pauta_mecanicos") == "2"
    pg.sql("DELETE FROM taller_solicitud_pauta_mecanicos WHERE mecanico_id = 3")
    pg.sql(migration_sql("downgrade"))
    assert pg.sql("SELECT mecanico_id FROM taller_solicitud_pauta WHERE id = 1") == "2"
    pg.sql(migration_sql("upgrade"))
    assert pg.sql("SELECT pauta_id, mecanico_id FROM taller_solicitud_pauta_mecanicos") == "1|2"
    with pytest.raises(AssertionError):
        pg.sql("INSERT INTO taller_solicitud_pauta_mecanicos VALUES (1, 2)")
    with pytest.raises(AssertionError):
        pg.sql("INSERT INTO taller_solicitud_pauta_mecanicos VALUES (1, 999)")
    pg.sql("DELETE FROM taller_solicitud_pauta WHERE id = 1")
    assert pg.sql("SELECT count(*) FROM taller_solicitud_pauta_mecanicos") == "0"
