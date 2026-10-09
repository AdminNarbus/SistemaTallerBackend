"""Corrector de datos contra PostgreSQL local, en un esquema descartable con rollback."""
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.base import Base
from app.core.config import settings
import app.models
from scripts.fix_visitas_falsas_ot import corregir, validar_url, preparar_archivo


@pytest.fixture
def pg_corrector():
    # El guard rechaza un DATABASE_URL remoto antes de abrir una conexión.
    engine = create_engine(validar_url(settings.sync_database_url), connect_args={"connect_timeout": 10})
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = "test_fix_visitas_" + uuid.uuid4().hex
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            Base.metadata.create_all(connection)
            connection.execute(text("INSERT INTO roles(id,nombre) VALUES (1,'SUPERVISOR')"))
            connection.execute(text("INSERT INTO usuarios(id,username,password_hash,rol_id) VALUES (1,'test','test',1)"))
            for ot_id, bus in ((3, "377"), (43, "391"), (99, "999")):
                connection.execute(text("INSERT INTO buses(id,n_bus,patente,en_taller) VALUES (:id,:bus,:bus,true)"), {"id": ot_id, "bus": bus})
                connection.execute(text("""INSERT INTO taller_solicitudes
                    (id,n_bus,bus_id,estado,fecha_creacion,fecha_primer_ingreso_taller,horas_demora_primer_ingreso,horas_taller_acumuladas)
                    VALUES (:id,:bus,:id,'PENDIENTE',now(),now(),0,0)"""), {"id": ot_id, "bus": bus})
                connection.execute(text("INSERT INTO taller_solicitud_estadias(id,solicitud_id,numero_visita,fecha_ingreso) VALUES (:id,:id,1,now())"), {"id": ot_id})
            connection.execute(text("""CREATE FUNCTION narbus_proteger_historial() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Historial protegido'; END $$"""))
            connection.execute(text("""CREATE TRIGGER tr_estadias_no_borrar BEFORE DELETE
                ON taller_solicitud_estadias FOR EACH ROW EXECUTE FUNCTION narbus_proteger_historial()"""))
            connection.execute(text("DROP TABLE taller_correcciones_visitas"))
            preparar_archivo(connection)
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


def _proteccion(connection):
    return connection.scalar(text("""SELECT tgenabled FROM pg_trigger
        WHERE tgrelid='taller_solicitud_estadias'::regclass AND tgname='tr_estadias_no_borrar'"""))


def test_corrige_archiva_y_no_repite_ni_toca_ot_ajena(pg_corrector):
    c = pg_corrector
    resultado = corregir(c, {3: "377", 43: "391"})
    assert resultado == {"corregidas": [3, 43], "ya_corregidas": []}
    assert c.scalar(text("SELECT count(*) FROM taller_solicitud_estadias")) == 1
    assert c.scalar(text("SELECT solicitud_id FROM taller_solicitud_estadias")) == 99
    for ot in (3, 43):
        row = c.execute(text("SELECT * FROM taller_solicitudes WHERE id=:id"), {"id": ot}).mappings().one()
        assert row["fecha_primer_ingreso_taller"] is None
        assert row["horas_demora_primer_ingreso"] is None
        assert row["horas_taller_acumuladas"] == 0
        assert row["estado"] == "PENDIENTE"
        assert c.scalar(text("SELECT en_taller FROM buses WHERE id=:id"), {"id": ot}) is False
        original = c.scalar(text("SELECT datos_originales FROM taller_correcciones_visitas WHERE solicitud_id=:id"), {"id": ot})
        assert original["estadias"][0]["id"] == ot
        assert original["bus_original"]["en_taller"] is True
        assert original["solicitud_original"]["fecha_primer_ingreso_taller"] is not None
    assert c.scalar(text("SELECT en_taller FROM buses WHERE id=99")) is True
    assert _proteccion(c) == "O"
    with pytest.raises(DBAPIError):
        with c.begin_nested():
            c.execute(text("DELETE FROM taller_correcciones_visitas"))
    assert corregir(c, {3: "377", 43: "391"}) == {"corregidas": [], "ya_corregidas": [3, 43]}
    # Una visita real posterior no debe ser retirada en una segunda ejecución.
    c.execute(text("INSERT INTO taller_solicitud_estadias(solicitud_id,numero_visita,fecha_ingreso) VALUES (3,1,now())"))
    assert corregir(c, {3: "377"})["corregidas"] == []
    assert c.scalar(text("SELECT count(*) FROM taller_solicitud_estadias WHERE solicitud_id=3")) == 1


@pytest.mark.parametrize("motivo", ["comentario", "bus_distinto", "ingreso_posterior", "en_reparacion", "dos_visitas"])
def test_rechaza_datos_que_no_corresponden_sin_cambios_parciales(pg_corrector, motivo):
    c = pg_corrector
    bus = "391"
    if motivo == "comentario":
        c.execute(text("INSERT INTO taller_solicitud_comentarios(solicitud_id,usuario_id,comentario) VALUES (43,1,'Observación')"))
    elif motivo == "bus_distinto":
        bus = "OTRO"
    elif motivo == "ingreso_posterior":
        c.execute(text("UPDATE taller_solicitud_estadias SET fecha_ingreso=fecha_ingreso + interval '1 hour' WHERE solicitud_id=43"))
    elif motivo == "en_reparacion":
        c.execute(text("UPDATE taller_solicitudes SET estado='EN_REPARACION' WHERE id=43"))
    else:
        c.execute(text("INSERT INTO taller_solicitud_estadias(solicitud_id,numero_visita,fecha_ingreso,fecha_salida) VALUES (43,2,now(),now())"))
    with pytest.raises(ValueError):
        with c.begin_nested():
            corregir(c, {3: "377", 43: bus})
    assert c.scalar(text("SELECT count(*) FROM taller_solicitud_estadias WHERE solicitud_id=3")) == 1
    assert c.scalar(text("SELECT fecha_primer_ingreso_taller IS NOT NULL FROM taller_solicitudes WHERE id=3"))
    assert _proteccion(c) == "O"


def test_error_despues_del_borrado_restaura_datos_y_trigger(pg_corrector):
    c = pg_corrector
    c.execute(text("""CREATE FUNCTION fallar_segunda_ot() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF OLD.solicitud_id=43 THEN RAISE EXCEPTION 'Fallo simulado'; END IF; RETURN OLD; END $$"""))
    c.execute(text("""CREATE TRIGGER fallo_prueba AFTER DELETE ON taller_solicitud_estadias
        FOR EACH ROW EXECUTE FUNCTION fallar_segunda_ot()"""))
    with pytest.raises(DBAPIError):
        with c.begin_nested():
            corregir(c, {3: "377", 43: "391"})
    assert c.scalar(text("SELECT count(*) FROM taller_solicitud_estadias")) == 3
    assert c.scalar(text("SELECT bool_and(en_taller) FROM buses")) is True
    assert c.scalar(text("SELECT bool_and(fecha_primer_ingreso_taller IS NOT NULL) FROM taller_solicitudes")) is True
    assert _proteccion(c) == "O"


def test_destino_remoto_se_rechaza_antes_de_conectar():
    with pytest.raises(ValueError, match="localhost"):
        validar_url("postgresql://example.invalid/taller")


def test_preparar_archivo_es_idempotente(pg_corrector):
    c = pg_corrector
    preparar_archivo(c)
    preparar_archivo(c)
    assert c.scalar(text("SELECT count(*) FROM taller_correcciones_visitas")) == 0
