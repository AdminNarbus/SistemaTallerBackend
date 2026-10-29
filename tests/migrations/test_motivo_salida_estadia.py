"""Regresión de longitud en PostgreSQL temporal, sin conectar a la BD de la app."""
import importlib.util
import io
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture(scope="module")
def postgres_temporal():
    from test_jsonb_migrations import JsonCompatibility, PG_BIN

    if not (PG_BIN / "initdb.exe").is_file():
        pytest.skip("Requiere binarios locales de PostgreSQL")
    try:
        JsonCompatibility.setUpClass()
        yield JsonCompatibility()
    finally:
        JsonCompatibility.doClassCleanups()


def migration_sql(direction: str) -> str:
    path = Path(__file__).resolve().parents[2] / "alembic/versions/032_ampliar_motivo_salida_estadia.py"
    spec = importlib.util.spec_from_file_location("motivo_salida_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )
    with Operations.context(context):
        getattr(migration, direction)()
    return output.getvalue()


def test_migracion_conserva_motivos_y_revierte_sin_truncar(postgres_temporal):
    postgres = postgres_temporal
    motivo = "Liberación / Egreso de taller desde Gestión de Flota"
    postgres.sql("""
        CREATE TABLE taller_solicitud_estadias (id integer PRIMARY KEY, motivo_salida varchar(50));
        INSERT INTO taller_solicitud_estadias VALUES (1, 'LIBERADO'), (2, NULL);
        DO $$ BEGIN
            UPDATE taller_solicitud_estadias SET motivo_salida = repeat(chr(225), 51) WHERE id = 1;
            RAISE EXCEPTION 'El esquema previo debe rechazar el motivo largo';
        EXCEPTION WHEN string_data_right_truncation THEN NULL;
        END $$;
    """)

    postgres.sql(migration_sql("upgrade"))
    assert postgres.sql("SELECT motivo_salida FROM taller_solicitud_estadias WHERE id = 1") == "LIBERADO"
    assert postgres.sql("SELECT motivo_salida IS NULL FROM taller_solicitud_estadias WHERE id = 2") == "t"
    # SQL ASCII evita depender de la codificación de stdin de psql en Windows.
    postgres.sql(f"""UPDATE taller_solicitud_estadias
        SET motivo_salida = convert_from(decode('{motivo.encode('utf-8').hex()}', 'hex'), 'UTF8') WHERE id = 1""")
    motivo_hex = "SELECT encode(convert_to(motivo_salida, 'UTF8'), 'hex') FROM taller_solicitud_estadias WHERE id = 1"
    assert postgres.sql(motivo_hex) == motivo.encode("utf-8").hex()
    postgres.sql("INSERT INTO taller_solicitud_estadias VALUES (3, repeat(chr(225), 1000))")
    assert postgres.sql("SELECT length(motivo_salida) FROM taller_solicitud_estadias WHERE id = 3") == "1000"

    # Una reversión incompatible debe fallar sin perder motivos ya guardados.
    with pytest.raises(AssertionError):
        postgres.sql(migration_sql("downgrade"))
    assert postgres.sql(motivo_hex) == motivo.encode("utf-8").hex()
    assert postgres.sql("SELECT length(motivo_salida) FROM taller_solicitud_estadias WHERE id = 3") == "1000"

    # Datos compatibles permiten el ciclo downgrade / upgrade completo.
    postgres.sql("UPDATE taller_solicitud_estadias SET motivo_salida = 'LIBERADO' WHERE motivo_salida IS NOT NULL")
    postgres.sql(migration_sql("downgrade"))
    assert postgres.sql("""SELECT character_maximum_length FROM information_schema.columns
        WHERE table_name = 'taller_solicitud_estadias' AND column_name = 'motivo_salida'""") == "50"
    postgres.sql(migration_sql("upgrade"))
    assert postgres.sql("""SELECT data_type FROM information_schema.columns
        WHERE table_name = 'taller_solicitud_estadias' AND column_name = 'motivo_salida'""") == "text"
