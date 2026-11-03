"""Carga opcional y exclusiva local del snapshot simulado del Dashboard.

Revision ID: 032_dashboard_simulados_local
Revises: 031_depuracion_supervision

Activar con: alembic -x dashboard_simulados=1 upgrade head
Sin esa opción la revisión no inserta datos (incluido el arranque productivo).
"""
import gzip
import json
import logging
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import context, op

revision = "032_dashboard_simulados_local"
down_revision = "031_depuracion_supervision"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")
OFFSET = 1_000_000
ACTOR_ID = OFFSET
ACTOR_NAME = "Simulación Dashboard"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data/dashboard_simulados_20261027.json.gz"
ORDER = (
    "usuarios", "talleres", "taller_solicitudes", "taller_solicitud_detalles",
    "taller_solicitud_estadias", "taller_solicitud_mecanicos", "taller_asignacion_fallas",
    "taller_falla_eventos", "taller_resultado_operaciones", "taller_resultado_ubicaciones",
)
USER_FIELDS = {"usuario_creador_id", "mecanico_cierre_id", "mecanico_resolvio_id",
               "reportado_por_id", "mecanico_id", "asignado_por_id", "usuario_actor_id", "actor_id"}
SHIFT_FIELDS = {"id", "solicitud_id", "detalle_id", "evento_id", "taller_id"} | USER_FIELDS


def read_snapshot():
    return json.loads(gzip.decompress(SNAPSHOT.read_bytes()))


def require_local(bind):
    if bind.dialect.name != "postgresql" or bind.engine.url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("La simulación solo puede cargarse en PostgreSQL de loopback.")
    from app.core.config import settings
    if settings.ENVIRONMENT.value != "dev_local":
        raise RuntimeError("La simulación requiere ENVIRONMENT=dev_local.")


def reference_maps(bind, data):
    buses = dict(bind.execute(sa.text("SELECT trim(n_bus), id FROM buses")).all())
    cities = dict(bind.execute(sa.text("SELECT codigo, id FROM ciudades")).all())
    roles = dict(bind.execute(sa.text("SELECT nombre, id FROM roles")).all())
    return {
        "bus_id": {r["id"]: buses[str(r["n_bus"]).strip()] for r in data["referencias"]["buses"]},
        "ciudad_id": {r["id"]: cities[r["codigo"]] for r in data["referencias"]["ciudades"]},
        "rol_id": {r["id"]: roles[r["nombre"]] for r in data["referencias"]["roles"]},
    }


def user_rows(data, maps):
    rows = [{"id": ACTOR_ID, "nombre": ACTOR_NAME, "apellido": None,
             "username": "simulacion.dashboard", "rol_id": maps["rol_id"][1]}]
    for user in data["referencias"]["usuarios"]:
        rows.append({"id": OFFSET + user["id"], "nombre": user["nombre"],
                     "apellido": user["apellido"], "username": f"simulacion.dashboard.{user['id']}",
                     "rol_id": maps["rol_id"][user["rol_id"]]})
    for row in rows:
        row.update(is_active=False, password_hash="!simulacion-sin-acceso")
    return rows


def transform_row(row, maps):
    result = {}
    for key, value in row.items():
        if value is not None and key in maps:
            value = maps[key][value]
        elif value is not None and key == "ciudad_id_snapshot":
            value = maps["ciudad_id"][value]
        elif value is not None and key in SHIFT_FIELDS:
            value += OFFSET
        result[key] = value
    return result


def adapt_rows(name, rows):
    if name == "taller_falla_eventos":
        for row in rows:
            row.update(actor_nombre_snapshot=ACTOR_NAME, usuario_actor_id=ACTOR_ID)
    if name == "taller_asignacion_fallas":
        for row in rows:
            row.update(origen="SUPERVISOR", asignado_por_id=ACTOR_ID,
                       comentario="SIMULACION: origen original SIMULACION; adaptación al catálogo permitido.")
    if name in {"taller_resultado_operaciones", "taller_resultado_ubicaciones"}:
        for row in rows:
            row["actor_id"] = ACTOR_ID
    if name == "taller_resultado_operaciones":
        for row in rows:
            row["respuesta"] = {"simulado": True, "origen": "Dashboard", "detalle_id": row["detalle_id"]}
    if name == "taller_solicitud_mecanicos":
        return deduplicate_active_crews(rows)
    return rows


def deduplicate_active_crews(rows):
    seen, result = {}, []
    for row in rows:
        key = (row["solicitud_id"], row["mecanico_id"])
        if row["is_activo"] and key in seen:
            if {k: v for k, v in row.items() if k != "id"} != seen[key]:
                raise RuntimeError("Cuadrillas activas incompatibles; no es un duplicado exacto.")
            continue
        if row["is_activo"]:
            seen[key] = {k: v for k, v in row.items() if k != "id"}
        result.append(row)
    return result


def prepare_rows(data, maps):
    result = {"usuarios": user_rows(data, maps)}
    for name in ORDER[1:]:
        rows = [transform_row(row, maps) for row in data["tablas"].get(name, [])]
        result[name] = adapt_rows(name, rows)
    return result


def insert_rows(bind, table, rows):
    for row in rows:
        clean = {k: v for k, v in row.items() if k in table.c}
        for key in tuple(clean):
            column = table.c[key]
            if clean[key] is None and column.server_default is not None and not column.nullable:
                del clean[key]
            elif isinstance(column.type, sa.DateTime) and isinstance(clean[key], str):
                clean[key] = datetime.fromisoformat(clean[key])
        bind.execute(table.insert().values(**clean))


def sync_sequence(bind, name):
    # Los IDs explícitos no avanzan SERIAL; nunca retroceder una secuencia.
    sequence = bind.execute(sa.text("SELECT pg_get_serial_sequence(:name, 'id')"), {"name": name}).scalar()
    if sequence:
        bind.execute(sa.text(
            f"SELECT setval(:seq, GREATEST((SELECT COALESCE(max(id), 1) FROM {name}), "
            "pg_sequence_last_value(CAST(:seq AS regclass))), true)"
        ), {"seq": sequence})


def upgrade():
    if context.get_x_argument(as_dictionary=True).get("dashboard_simulados") != "1":
        logger.info("Snapshot Dashboard omitido: requiere -x dashboard_simulados=1")
        return
    bind = op.get_bind()
    require_local(bind)
    # Carga inicial: impedir mezclas y colisiones con trabajo operacional previo.
    if bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM taller_solicitudes)")).scalar():
        raise RuntimeError("La carga inicial requiere una base sin órdenes de trabajo.")
    data = read_snapshot()
    maps = reference_maps(bind, data)
    bus_ids = list(maps["bus_id"].values())
    if bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM buses WHERE id = ANY(:ids) AND en_taller)"), {"ids": bus_ids}).scalar():
        raise RuntimeError("Los buses de destino ya tienen marcas de taller; revisar antes de cargar.")
    rows = prepare_rows(data, maps)
    metadata = sa.MetaData()
    for name in ORDER:
        table = sa.Table(name, metadata, autoload_with=bind)
        insert_rows(bind, table, rows[name])
        if "id" in table.c:
            sync_sequence(bind, name)
        logger.info("Dashboard simulado: %s = %s filas", name, len(rows[name]))


def downgrade():
    bind = op.get_bind()
    # La presencia del actor determina si se activó la carga en esta base.
    actor = bind.execute(sa.text("SELECT username FROM usuarios WHERE id=:id"), {"id": ACTOR_ID}).scalar()
    if actor != "simulacion.dashboard":
        return
    require_local(bind)
    data = read_snapshot()
    maps = reference_maps(bind, data)
    rows = prepare_rows(data, maps)
    bind.execute(sa.text("SET LOCAL narbus.permitir_depuracion = 'on'"))
    metadata = sa.MetaData()
    for name in reversed(ORDER):
        table = sa.Table(name, metadata, autoload_with=bind)
        key = "operacion_id" if name == "taller_resultado_operaciones" else "id"
        ids = [row[key] for row in rows[name]]
        bind.execute(table.delete().where(table.c[key].in_(ids)))
    bind.execute(sa.text("""
        UPDATE buses b SET en_taller=EXISTS (
            SELECT 1 FROM taller_solicitud_estadias e
            JOIN taller_solicitudes s ON s.id=e.solicitud_id
            WHERE s.bus_id=b.id AND s.estado <> 'FINALIZADO' AND e.fecha_salida IS NULL
        ) WHERE b.id=ANY(:ids)
    """), {"ids": list(maps["bus_id"].values())})
