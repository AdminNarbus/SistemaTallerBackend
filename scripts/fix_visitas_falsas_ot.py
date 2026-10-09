"""Corregir ingresos automáticos de OTs confirmadas como nunca ingresadas al taller.

Consulta local: python -m scripts.fix_visitas_falsas_ot --ot 3:377 --ot 43:391
Aplicación: agregar --aplicar. Para uso remoto posterior se exige --permitir-remoto.
No toma conexiones de los scripts de mantenimiento ni contiene credenciales.
"""
import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


TABLES = (
    "taller_solicitudes", "buses", "taller_solicitud_estadias",
    "taller_solicitud_comentarios", "taller_solicitud_mecanicos",
    "taller_asignacion_fallas", "taller_solicitud_detalles",
    "taller_solicitud_pauta", "taller_solicitud_estado_eventos", "taller_falla_eventos",
)

AUDIT_SQL = """
SELECT s.id, s.n_bus, s.bus_id, row_to_json(s)::jsonb AS solicitud_original,
       row_to_json(b)::jsonb AS bus_original,
       COALESCE((SELECT jsonb_agg(to_jsonb(e) ORDER BY e.numero_visita)
                 FROM taller_solicitud_estadias e WHERE e.solicitud_id=s.id), '[]'::jsonb) AS estadias,
       (SELECT count(*) FROM taller_solicitud_comentarios c WHERE c.solicitud_id=s.id) AS comentarios,
       (SELECT count(*) FROM taller_solicitud_mecanicos m WHERE m.solicitud_id=s.id) AS mecanicos,
       (SELECT count(*) FROM taller_asignacion_fallas a WHERE a.solicitud_id=s.id) AS asignaciones,
       (SELECT count(*) FROM taller_solicitud_pauta p WHERE p.solicitud_id=s.id) AS pauta,
       (SELECT count(*) FROM taller_solicitud_estado_eventos v
        WHERE v.solicitud_id=s.id AND v.tipo_evento <> 'CREACION') AS cambios_estado,
       (SELECT count(*) FROM taller_solicitud_detalles d WHERE d.solicitud_id=s.id
        AND (d.resuelto OR COALESCE(d.estado, 'PENDIENTE') <> 'PENDIENTE'
             OR d.mecanico_resolvio_id IS NOT NULL OR d.fecha_resolucion IS NOT NULL)) AS fallas_atendidas,
       (SELECT count(*) FROM taller_falla_eventos f JOIN taller_solicitud_detalles d ON d.id=f.detalle_id
        WHERE d.solicitud_id=s.id AND f.tipo_evento <> 'REPORTADA') AS eventos_trabajo
FROM taller_solicitudes s LEFT JOIN buses b ON b.id=s.bus_id
WHERE (:ot_id IS NULL OR s.id=CAST(:ot_id AS integer)) ORDER BY s.id
"""


def _fecha(value):
    fecha = datetime.fromisoformat(value) if isinstance(value, str) else value
    return fecha.replace(tzinfo=timezone.utc) if fecha.tzinfo is None else fecha.astimezone(timezone.utc)


def motivos_rechazo(row, bus_esperado):
    """El patrón permite proponer candidatos; la selección explícita confirma el error."""
    motivos = []
    solicitud = row["solicitud_original"]
    if bus_esperado is not None and row["n_bus"].strip().casefold() != bus_esperado.strip().casefold():
        motivos.append("el número de bus no coincide con el indicado")
    if solicitud["estado"] not in ("PENDIENTE", "REPORTADO"):
        motivos.append("la OT no está pendiente/reportada")
    if solicitud.get("fecha_cierre") or solicitud.get("fecha_liberacion"):
        motivos.append("la OT registra cierre o liberación")
    if float(solicitud.get("horas_taller_acumuladas") or 0) != 0:
        motivos.append("hay horas acumuladas de taller")
    if solicitud.get("horas_demora_primer_ingreso") is None or float(solicitud["horas_demora_primer_ingreso"]) != 0:
        motivos.append("la demora inicial no corresponde al ingreso automático")
    creacion = _fecha(solicitud["fecha_creacion"])
    primer_ingreso = solicitud.get("fecha_primer_ingreso_taller")
    if primer_ingreso is None or _fecha(primer_ingreso) != creacion:
        motivos.append("el primer ingreso no coincide exactamente con la creación")
    estadias = row["estadias"]
    if len(estadias) != 1:
        motivos.append("no existe exactamente una visita")
    else:
        visita = estadias[0]
        if (visita["numero_visita"] != 1 or visita.get("fecha_salida") is not None
                or visita.get("horas_estadia") is not None or visita.get("motivo_salida") is not None
                or _fecha(visita["fecha_ingreso"]) != creacion):
            motivos.append("la visita no corresponde a una primera visita automática abierta")
    for campo in ("comentarios", "mecanicos", "asignaciones", "pauta", "cambios_estado", "fallas_atendidas", "eventos_trabajo"):
        if row[campo]:
            motivos.append(f"hay registros en {campo}")
    return motivos


def validar_url(raw, permitir_remoto=False):
    url = make_url(raw)
    if url.get_backend_name() != "postgresql":
        raise ValueError("El corrector requiere PostgreSQL.")
    if url.host not in ("localhost", "127.0.0.1", "::1") and not permitir_remoto:
        raise ValueError("Solo se permite localhost. El uso remoto posterior exige --permitir-remoto.")
    query = dict(url.query)
    if "ssl" in query:
        query["sslmode"] = query.pop("ssl")
    return url.set(drivername="postgresql+psycopg2", query=query)


def preparar_archivo(connection):
    """Crear el archivo desde el script, sin añadir revisiones a Alembic."""
    from app.modules.taller.models.taller_correccion_visita import TallerCorreccionVisita
    TallerCorreccionVisita.__table__.create(connection, checkfirst=True)
    if connection.scalar(text("SELECT to_regproc('narbus_proteger_historial')")) is not None:
        for nombre, evento, nivel in (
            ("tr_correcciones_visitas_inmutables", "UPDATE OR DELETE", "ROW"),
            ("tr_correcciones_visitas_no_truncate", "TRUNCATE", "STATEMENT"),
        ):
            existe = connection.scalar(text("""SELECT 1 FROM pg_trigger
                WHERE tgrelid='taller_correcciones_visitas'::regclass AND tgname=:nombre"""), {"nombre": nombre})
            if not existe:
                connection.execute(text(f"CREATE TRIGGER {nombre} BEFORE {evento} ON taller_correcciones_visitas FOR EACH {nivel} EXECUTE FUNCTION narbus_proteger_historial()"))


def corregir(connection, objetivos):
    """Una sola transacción: validar todos, archivar, retirar visitas y recalcular buses."""
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '60s'"))
    # Impide que se registre trabajo entre la validación y la corrección, y
    # protege a otros escritores mientras se suspende el trigger de borrado.
    connection.execute(text("LOCK TABLE " + ", ".join(TABLES) + " IN SHARE ROW EXCLUSIVE MODE"))
    preparar_archivo(connection)
    pendientes, omitidas = [], []
    for ot_id, bus_esperado in objetivos.items():
        archivada = connection.scalar(text("SELECT 1 FROM taller_correcciones_visitas WHERE solicitud_id=:id"), {"id": ot_id})
        row = connection.execute(text(AUDIT_SQL), {"ot_id": ot_id}).mappings().one_or_none()
        if row is None:
            raise ValueError(f"OT {ot_id}: no existe; se cancela toda la operación.")
        if row["n_bus"].strip().casefold() != bus_esperado.strip().casefold():
            raise ValueError(f"OT {ot_id}: el bus no coincide; se cancela toda la operación.")
        if archivada:
            omitidas.append(ot_id)
            continue
        rechazos = motivos_rechazo(row, bus_esperado)
        if rechazos:
            raise ValueError(f"OT {ot_id}: " + "; ".join(rechazos) + ". No se aplicó ninguna corrección.")
        pendientes.append(dict(row))

    trigger = connection.execute(text("""SELECT t.tgenabled, p.proname FROM pg_trigger t
        JOIN pg_proc p ON p.oid=t.tgfoid
        WHERE t.tgrelid='taller_solicitud_estadias'::regclass AND t.tgname='tr_estadias_no_borrar'""")).first()
    if trigger and (trigger.tgenabled != "O" or trigger.proname != "narbus_proteger_historial"):
        raise ValueError("La protección de estadías no está en su configuración esperada.")
    if trigger and pendientes:
        connection.execute(text("ALTER TABLE taller_solicitud_estadias DISABLE TRIGGER tr_estadias_no_borrar"))
    for row in pendientes:
        visita = row["estadias"][0]
        connection.execute(text("""INSERT INTO taller_correcciones_visitas
            (solicitud_id,estadia_id,motivo,datos_originales)
            VALUES (:ot,:estadia,:motivo,CAST(:datos AS jsonb))"""), {
                "ot": row["id"], "estadia": visita["id"],
                "motivo": "Ingreso automático al crear OT; confirmado que el bus nunca ingresó al taller.",
                "datos": json.dumps(row, default=str, ensure_ascii=False),
            })
        connection.execute(text("DELETE FROM taller_solicitud_estadias WHERE id=:id AND solicitud_id=:ot"), {"id": visita["id"], "ot": row["id"]})
        connection.execute(text("""UPDATE taller_solicitudes SET fecha_primer_ingreso_taller=NULL,
            horas_demora_primer_ingreso=NULL, horas_taller_acumuladas=0, fecha_actualizacion=now()
            WHERE id=:id"""), {"id": row["id"]})
    if trigger and pendientes:
        connection.execute(text("ALTER TABLE taller_solicitud_estadias ENABLE TRIGGER tr_estadias_no_borrar"))
    for bus_id in {r["bus_id"] for r in pendientes if r["bus_id"] is not None}:
        connection.execute(text("""UPDATE buses b SET en_taller=EXISTS (
            SELECT 1 FROM taller_solicitud_estadias e JOIN taller_solicitudes s ON s.id=e.solicitud_id
            WHERE s.bus_id=b.id AND s.estado <> 'FINALIZADO' AND e.fecha_salida IS NULL
        ) WHERE b.id=:id"""), {"id": bus_id})
    return {"corregidas": [r["id"] for r in pendientes], "ya_corregidas": omitidas}


def _objetivo(value):
    try:
        ot, bus = value.split(":", 1)
        ot = int(ot)
        if ot <= 0 or not bus.strip():
            raise ValueError
        return ot, bus.strip()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use ID_OT:NUMERO_BUS, por ejemplo 3:377.") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ot", action="append", type=_objetivo, default=[], help="OT y bus confirmados como nunca ingresados: 3:377. Repetible.")
    parser.add_argument("--aplicar", action="store_true", help="Aplicar correcciones y archivar originales; sin este argumento solo se consulta.")
    parser.add_argument("--permitir-remoto", action="store_true", help="Habilitar explícitamente el uso remoto posterior.")
    args = parser.parse_args()
    objetivos = dict(args.ot)
    if len(objetivos) != len(args.ot):
        parser.error("No repita una OT en la selección.")
    if args.aplicar and not objetivos:
        parser.error("--aplicar exige seleccionar cada OT confirmada mediante --ot ID:BUS.")
    from app.core.config import settings
    # Validar el destino antes de crear la conexión; nunca imprimir credenciales.
    try:
        url = validar_url(settings.sync_database_url, args.permitir_remoto)
    except ValueError as exc:
        parser.error(str(exc))
    engine = create_engine(url, connect_args={"connect_timeout": 10})
    try:
        with engine.begin() as connection:
            if args.aplicar:
                resultado = corregir(connection, objetivos)
            else:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                for ot_id in objetivos or {None: None}:
                    rows = connection.execute(text(AUDIT_SQL), {"ot_id": ot_id}).mappings().all()
                    if not rows:
                        print(f"OT {ot_id}: no existe en esta base.")
                    for row in rows:
                        rechazos = motivos_rechazo(row, objetivos.get(ot_id))
                        if objetivos or not rechazos:
                            print(json.dumps({"ot": row["id"], "bus": row["n_bus"],
                                "candidata": not rechazos, "rechazos": rechazos}, ensure_ascii=False))
        if args.aplicar:
            print(json.dumps(resultado, ensure_ascii=False))
    except ValueError as exc:
        parser.exit(1, str(exc) + "\n")
    except SQLAlchemyError:
        parser.exit(1, "No se pudo completar la operación en PostgreSQL. La transacción fue revertida. Revisar conexión, revisión de esquema y permisos.\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
