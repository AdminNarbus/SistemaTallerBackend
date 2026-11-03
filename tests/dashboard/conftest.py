"""Datos mínimos aislados; nunca se usa la conexión operacional."""

from datetime import datetime, time, timedelta, timezone
import re
import statistics
import unicodedata
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_db, require_supervisor_or_admin
from app.core.base import Base
from app.main import app
from app.modules.dashboard.repository.relations import A, B, D, E, EM, L, M, R, S, SE, U, V

ZONE = ZoneInfo("America/Santiago")


def instant(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def local_day(value):
    return instant(value).astimezone(ZONE).date() if value else None


def normalized(value):
    if value is None:
        return None
    raw = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", raw).strip() or None


class MedianAggregate:
    def __init__(self):
        self.values = []

    def step(self, value):
        if value is not None:
            self.values.append(value)

    def finalize(self):
        return statistics.median(self.values) if self.values else None


def register_sqlite(connection, _):
    functions = {
        "localday": (1, lambda x: local_day(x).isoformat() if x else None),
        "monthkey": (1, lambda x: local_day(x).strftime("%Y-%m") if x else None),
        "weekkey": (
            1,
            lambda x: (
                (local_day(x) - timedelta(days=local_day(x).weekday())).isoformat() if x else None
            ),
        ),
        "buskey": (
            1,
            lambda x: (
                re.sub(r"^0+(?=\d)", "", re.sub(r"^#\s*", "", x.strip())) or None if x else None
            ),
        ),
        "normalized": (1, normalized),
        "hours": (
            2,
            lambda a, b: (instant(b) - instant(a)).total_seconds() / 3600 if a and b else None,
        ),
        "endofday": (
            1,
            lambda x: (
                (
                    datetime.combine(
                        datetime.fromisoformat(x).date() + timedelta(days=1), time.min, ZONE
                    ).astimezone(timezone.utc)
                    - timedelta(microseconds=1)
                ).isoformat()
                if x
                else None
            ),
        ),
    }
    for name, (arity, callback) in functions.items():
        connection.create_function(f"dashboard_{name}", arity, callback)
    connection.run_async(
        lambda raw: raw._execute(raw._conn.create_aggregate, "dashboard_median", 1, MedianAggregate)
    )


@pytest.fixture
async def dashboard_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    event.listen(engine.sync_engine, "connect", register_sqlite)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def dashboard_client(dashboard_db):
    saved = dict(app.dependency_overrides)

    async def database():
        yield dashboard_db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_supervisor_or_admin] = lambda: object()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def at(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


@pytest.fixture
async def dashboard_data(dashboard_db):
    db = dashboard_db
    await db.execute(insert(R), [{"id": 1, "nombre": "MECANICO"}, {"id": 2, "nombre": "CONDUCTOR"}])
    await db.execute(
        insert(U),
        [
            {
                "id": 1001,
                "nombre": "Ana",
                "apellido": "Actual",
                "username": "ana",
                "password_hash": "never-expose",
                "rol_id": 1,
                "is_active": True,
            },
            {
                "id": 1002,
                "nombre": "Luis",
                "apellido": "Histórico",
                "username": "luis",
                "password_hash": "never-expose",
                "rol_id": 1,
                "is_active": False,
            },
            {
                "id": 1003,
                "nombre": "Conductor",
                "apellido": "Ejemplo",
                "username": "driver",
                "password_hash": "never-expose",
                "rol_id": 2,
                "is_active": True,
            },
        ],
    )
    await db.execute(
        insert(B),
        [
            {"id": 101, "n_bus": "001", "patente": "TEST-01", "is_active": True},
            {"id": 102, "n_bus": "2", "patente": "TEST-02", "is_active": True},
            {"id": 103, "n_bus": "3", "patente": "TEST-03", "is_active": False},
            {"id": 104, "n_bus": "4", "patente": "TEST-04", "is_active": True},
            {"id": 105, "n_bus": "0001", "patente": "TEST-05", "is_active": True},
        ],
    )
    specs = [
        (1, 101, "001", "FINALIZADO", "2026-09-30T23:00", "2026-10-02T15:00"),
        (2, 101, "001", "PENDIENTE", "2026-10-26T12:00", None),
        (3, 102, "2", "EN_REPARACION", "2026-10-25T12:00", None),
        (4, None, "999", "PENDIENTE", "2026-10-20T12:00", None),
        (5, 103, "3", "FINALIZADO", "2026-10-01T12:00", "2026-10-02T12:00"),
        (6, 102, "2", "FINALIZADO", "2026-09-28T12:00", "2026-09-29T12:00"),
        (7, None, "0002", "FINALIZADO", "2026-10-10T12:00", "2026-10-11T12:00"),
        (8, None, "1", "FINALIZADO", "2026-10-12T12:00", "2026-10-13T12:00"),
    ]
    orders = [
        {
            "id": i,
            "bus_id": bus,
            "n_bus": n,
            "estado": state,
            "es_ot": True,
            "fecha_creacion": at(created),
            "fecha_cierre": at(end) if end else None,
            "fecha_liberacion": at("2026-10-02T12:00") if i == 1 else None,
            "fecha_primer_ingreso_taller": at("2026-10-01T13:00") if i == 1 else None,
            "usuario_creador_id": 1003,
        }
        for i, bus, n, state, created, end in specs
    ]
    await db.execute(insert(S), orders)
    faults = [
        (11, 1, "RESUELTA", "Frenó no responde", "2026-09-30T23:00"),
        (12, 2, "PENDIENTE", "Freno no responde", "2026-10-26T12:00"),
        (13, 2, "INCOMPLETA", "Aire", "2026-10-26T12:00"),
        (31, 3, "RESUELTA", "Frenó", "2026-10-25T12:00"),
        (61, 6, "RESUELTA", "Freno", "2026-09-28T12:00"),
        (71, 7, "PENDIENTE", "Otra", "2026-10-10T12:00"),
    ]
    await db.execute(
        insert(D),
        [
            {
                "id": i,
                "solicitud_id": ot,
                "descripcion_personalizada": text,
                "estado": state,
                "resuelto": state == "RESUELTA",
                "fecha_reporte": at(date),
                "fecha_creacion": at(date),
                "reportado_por_id": 1003,
            }
            for i, ot, state, text, date in faults
        ],
    )
    await db.execute(
        insert(M),
        [
            {
                "id": 1,
                "solicitud_id": 1,
                "mecanico_id": 1001,
                "fecha_asignacion": at("2026-10-01T13:00"),
            },
            {
                "id": 2,
                "solicitud_id": 3,
                "mecanico_id": 1001,
                "fecha_asignacion": at("2026-10-25T10:00"),
            },
        ],
    )
    await db.execute(
        insert(A),
        [
            {
                "id": 1,
                "solicitud_id": 1,
                "detalle_id": 11,
                "mecanico_id": 1001,
                "fecha_asignacion": at("2026-10-01T13:00"),
            },
            {
                "id": 2,
                "solicitud_id": 1,
                "detalle_id": 11,
                "mecanico_id": 1002,
                "fecha_asignacion": at("2026-10-01T14:00"),
            },
        ],
    )
    await db.execute(
        insert(E),
        [
            {
                "id": 111,
                "detalle_id": 11,
                "tipo_evento": "REPORTADA",
                "estado_nuevo": "PENDIENTE",
                "actor_nombre_snapshot": "Chofer histórico",
                "fecha_evento": at("2026-09-30T23:00"),
            },
            {
                "id": 112,
                "detalle_id": 11,
                "tipo_evento": "RESUELTA",
                "estado_nuevo": "RESUELTA",
                "actor_nombre_snapshot": "Ana",
                "fecha_evento": at("2026-10-02T11:00"),
            },
            {
                "id": 313,
                "detalle_id": 31,
                "tipo_evento": "RESUELTA",
                "estado_nuevo": "RESUELTA",
                "actor_nombre_snapshot": "Luis",
                "fecha_evento": at("2026-10-25T14:00"),
            },
            {
                "id": 611,
                "detalle_id": 61,
                "tipo_evento": "RESUELTA",
                "estado_nuevo": "RESUELTA",
                "actor_nombre_snapshot": "Ana",
                "fecha_evento": at("2026-09-29T12:00"),
            },
        ],
    )
    await db.execute(
        insert(EM),
        [
            {
                "id": 1,
                "evento_id": 112,
                "mecanico_id": 1001,
                "mecanico_nombre_snapshot": "Nombre histórico",
            },
            {
                "id": 2,
                "evento_id": 313,
                "mecanico_id": 1002,
                "mecanico_nombre_snapshot": "Luis histórico",
            },
        ],
    )
    states = [
        (100, "CREACION", None, "PENDIENTE", "2026-09-30T23:00"),
        (101, "CAMBIO_ESTADO", "PENDIENTE", "EN_REPARACION", "2026-10-01T13:00"),
        (102, "CAMBIO_ESTADO", "EN_REPARACION", "LIBERADO", "2026-10-02T12:00"),
        (103, "CAMBIO_ESTADO", "LIBERADO", "FINALIZADO", "2026-10-02T15:00"),
    ]
    await db.execute(
        insert(SE),
        [
            {
                "id": i,
                "solicitud_id": 1,
                "tipo_evento": kind,
                "estado_anterior": before,
                "estado_nuevo": after,
                "fecha_evento": at(date),
                "actor_nombre_snapshot": "Supervisor",
                "origen": "OPERACION",
            }
            for i, kind, before, after, date in states
        ],
    )
    await db.execute(
        insert(V),
        [
            {
                "id": 1,
                "solicitud_id": 1,
                "numero_visita": 1,
                "fecha_ingreso": at("2026-10-01T13:00"),
                "fecha_salida": at("2026-10-02T12:00"),
            },
            {
                "id": 2,
                "solicitud_id": 2,
                "numero_visita": 1,
                "fecha_ingreso": at("2026-10-26T13:00"),
                "fecha_salida": None,
            },
            {
                "id": 3,
                "solicitud_id": 3,
                "numero_visita": 1,
                "fecha_ingreso": at("2026-10-25T13:00"),
                "fecha_salida": None,
            },
        ],
    )
    locations = [
        (1, 112, "INTERNO", "Temuco", "Narbus", "2026-10-02T12:00"),
        (2, 112, "EXTERNO", "Temuco", "Externo", "2026-10-03T12:00"),
        (3, 313, "INTERNO", "Santiago", "Narbus Santiago", "2026-10-25T14:00"),
        (4, 611, "INTERNO", "Valdivia", "Otro", "2026-09-29T12:00"),
    ]
    await db.execute(
        insert(L),
        [
            {
                "id": i,
                "evento_id": event_id,
                "version": 2 if i == 2 else 1,
                "taller_id": 1,
                "taller_nombre_snapshot": name,
                "taller_tipo_snapshot": kind,
                "ciudad_id_snapshot": 1,
                "ciudad_nombre_snapshot": city,
                "actor_id": 1001,
                "actor_nombre_snapshot": "Ana",
                "operacion_id": f"test-{i}",
                "registrado_en": at(date),
            }
            for i, event_id, kind, city, name, date in locations
        ],
    )
    await db.commit()
    return db
