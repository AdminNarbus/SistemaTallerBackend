"""Ciclo de migración de repuestos en PostgreSQL temporal."""
import importlib.util
import io
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from test_motivo_salida_estadia import postgres_temporal


def sql_migracion(accion):
    ruta = Path(__file__).resolve().parents[2] / "alembic/versions/038_repuestos_por_falla.py"
    spec = importlib.util.spec_from_file_location("repuestos_migration", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    output = io.StringIO()
    contexto = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(contexto):
        getattr(modulo, accion)()
    return output.getvalue()


def test_repuestos_upgrade_downgrade_y_restricciones(postgres_temporal):
    pg = postgres_temporal
    pg.sql("CREATE TABLE usuarios (id integer PRIMARY KEY); CREATE TABLE taller_solicitud_detalles (id integer PRIMARY KEY); INSERT INTO usuarios VALUES (1); INSERT INTO taller_solicitud_detalles VALUES (1);")
    pg.sql(sql_migracion("upgrade"))
    pg.sql("INSERT INTO repuestos (id,codigo,nombre) VALUES (1,'R1','Pieza'); INSERT INTO taller_repuestos_utilizados (falla_detalle_id,repuesto_id,cantidad_utilizada,usuario_registro_id,codigo_repuesto_al_registrar,nombre_repuesto_al_registrar,nombre_usuario_al_registrar) VALUES (1,1,2,1,'R1','Pieza','Usuario');")
    with pytest.raises(AssertionError):
        pg.sql("INSERT INTO taller_repuestos_utilizados (falla_detalle_id,repuesto_id,cantidad_utilizada,usuario_registro_id,codigo_repuesto_al_registrar,nombre_repuesto_al_registrar,nombre_usuario_al_registrar) VALUES (1,1,1,1,'R1','Pieza','Usuario')")
    with pytest.raises(AssertionError):
        pg.sql("DELETE FROM taller_solicitud_detalles WHERE id = 1")
    for sentencia in (
        "UPDATE taller_repuestos_utilizados SET cantidad_utilizada = 0",
        "UPDATE taller_repuestos_utilizados SET fecha_anulacion = CURRENT_TIMESTAMP",
        "UPDATE repuestos SET precio = -1",
        "UPDATE repuestos SET iva = -1",
        "DELETE FROM repuestos WHERE id = 1",
        "DELETE FROM usuarios WHERE id = 1",
        "UPDATE taller_repuestos_utilizados SET repuesto_id = 999999",
    ):
        with pytest.raises(AssertionError):
            pg.sql(sentencia)
    pg.sql("UPDATE taller_repuestos_utilizados SET fecha_anulacion = CURRENT_TIMESTAMP, usuario_anulacion_id = 1, nombre_usuario_al_anular = 'Usuario', motivo_anulacion = 'Error'")
    pg.sql("INSERT INTO taller_repuestos_utilizados (falla_detalle_id,repuesto_id,cantidad_utilizada,usuario_registro_id,codigo_repuesto_al_registrar,nombre_repuesto_al_registrar,nombre_usuario_al_registrar) VALUES (1,1,3,1,'R1','Pieza','Usuario')")
    assert pg.sql("SELECT count(*) FROM taller_repuestos_utilizados") == "2"
    pg.sql(sql_migracion("downgrade"))
    pg.sql(sql_migracion("upgrade"))
    assert pg.sql("SELECT count(*) FROM repuestos") == "0"
