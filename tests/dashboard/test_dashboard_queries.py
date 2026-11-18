from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, insert, literal, select, update

from app.modules.dashboard.repository.relations import D, S, SE, V
from app.modules.dashboard.repository.sql_expressions import (
    BusKey,
    EndOfDay,
    Hours,
    LocalDay,
    Normalized,
    WeekKey,
)

PREFIX = "/api/v1/dashboard"


@pytest.mark.parametrize(
    "query,expected",
    [
        ("seleccion_tipo=mecanico&seleccion_mecanico_id=1002", {1, 3}),
        ("seleccion_tipo=bus_fallas&seleccion_bus_id=101", {1, 2}),
        ("seleccion_tipo=bus_visitas&seleccion_bus_id=101", {1, 2}),
        ("seleccion_tipo=visitas_bus&seleccion_bus_id=101", {1, 2}),
        ("seleccion_tipo=creadas&seleccion_semana=2026-09-28", {1, 5, 6}),
        ("seleccion_tipo=terminadas&seleccion_semana=2026-09-28", {1, 5, 6}),
        ("seleccion_tipo=antiguedad&seleccion_grupo=HASTA_7_DIAS&meses=9", set()),
    ],
)
async def test_drilldown_matches_source_population(
    dashboard_client, dashboard_data, query, expected
):
    response = await dashboard_client.get(f"{PREFIX}/solicitudes?{query}")
    assert response.status_code == 200, response.text
    assert {row["id"] for row in response.json()["data"]["items"]} == expected


async def test_machine_summary_uses_current_history_independent_of_general_period(
    dashboard_client, dashboard_data
):
    response = await dashboard_client.get(f"{PREFIX}/buses/101/resumen?meses=9")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["estado"] == "PENDIENTE"
    assert response.json()["data"]["visitas"] == 2
    response = await dashboard_client.get(f"{PREFIX}/buses/101/cronologia/resumen?meses=9")
    assert response.json()["data"]["estado_actual"] == "PENDIENTE"


async def test_unknown_stage_state_and_stage_without_faults(dashboard_client, dashboard_data):
    response = await dashboard_client.get(f"{PREFIX}/buses/101/cronologia/detalles")
    assert response.status_code == 200, response.text
    unknown = [row for row in response.json()["data"]["items"] if row["detalle_id"] == 13]
    assert unknown[0]["estado_falla"] == "PENDIENTE"
    response = await dashboard_client.get(f"{PREFIX}/buses/103/cronologia/detalles")
    assert response.json()["data"]["total"] == 2
    assert all(row["detalle_id"] is None for row in response.json()["data"]["items"])


async def test_report_summary_covers_all_pages(dashboard_client, dashboard_data):
    first = await dashboard_client.get(f"{PREFIX}/buses/101/cronologia/detalles?limit=1")
    second = await dashboard_client.get(f"{PREFIX}/buses/101/cronologia/detalles?limit=1&skip=1")
    assert first.json()["data"]["items"] != second.json()["data"]["items"]
    response = await dashboard_client.get(f"{PREFIX}/buses/101/cronologia/resumen?limit=1")
    assert response.json()["data"]["fallas_distintas"] == 3


async def test_detail_queries_do_not_grow_per_milestone(dashboard_client, dashboard_data):
    counts = []
    for limit in (1, 100):
        sql = []

        def capture(_conn, _cursor, statement, *_):
            sql.append(statement)

        event.listen(dashboard_data.bind.sync_engine, "before_cursor_execute", capture)
        try:
            response = await dashboard_client.get(
                f"{PREFIX}/buses/101/cronologia/detalles?limit={limit}"
            )
        finally:
            event.remove(dashboard_data.bind.sync_engine, "before_cursor_execute", capture)
        assert response.status_code == 200, response.text
        counts.append(len(sql))
    assert counts == [4, 5]


async def test_santiago_calendar_dst_week_and_normalization(dashboard_db):
    stamp = literal(datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc))
    row = (
        await dashboard_db.execute(
            select(
                LocalDay(stamp),
                WeekKey(stamp),
                BusKey(literal(" # 0002 ")),
                Normalized(literal("Frenó\nNO responde🙂")),
            )
        )
    ).one()
    assert str(row[0]) == "2026-09-30"
    assert row[1:] == ("2026-09-28", "2", "freno no responde")
    duration = (
        await dashboard_db.execute(
            select(Hours(EndOfDay(literal("2026-09-05")), EndOfDay(literal("2026-09-06"))))
        )
    ).scalar_one()
    assert duration == 23.0


async def test_age_exact_groups_and_no_bus_no_current_state(dashboard_client, dashboard_data):
    now = datetime.now(timezone.utc)
    await dashboard_data.execute(
        update(S)
        .where(S.c.id == 2)
        .values(fecha_creacion=now - timedelta(days=3))
    )
    await dashboard_data.execute(
        update(S)
        .where(S.c.id == 1)
        .values(fecha_creacion=now - timedelta(days=50))
    )
    await dashboard_data.execute(
        update(S)
        .where(S.c.id == 3)
        .values(fecha_creacion=now - timedelta(days=14))
    )
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/series/antiguedad")
    assert response.status_code == 200, response.text
    assert {r["grupo"]: r["cantidad"] for r in response.json()["data"]["items"]} == {
        "HASTA_7_DIAS": 1,
        "MAS_7_HASTA_28_DIAS": 1,
        "MAS_28_DIAS": 0,
    }


async def test_filter_options_exclude_own_dimension_and_active_machine_master(
    dashboard_client, dashboard_data
):
    response = await dashboard_client.get(f"{PREFIX}/filtros/buses?bus_id=101")
    assert response.json()["data"]["total"] > 1
    response = await dashboard_client.get(f"{PREFIX}/filtros/solicitudes?solicitud_id=1")
    assert response.json()["data"]["total"] == 8
    response = await dashboard_client.get(f"{PREFIX}/filtros/buses?contexto=maquina")
    assert {r["bus_id"] for r in response.json()["data"]["items"]} == {101, 102, 104, 105}


async def test_fault_popover_group_and_related_orders(dashboard_client, dashboard_data):
    response = await dashboard_client.get(f"{PREFIX}/buses/101/fallas?estado_falla=PENDIENTE")
    assert response.json()["data"]["items"] == [{"descripcion": "Freno no responde", "cantidad": 1}]
    response = await dashboard_client.get(
        f"{PREFIX}/buses/101/fallas/solicitudes?estado_falla=PENDIENTE&descripcion=Freno%20no%20responde"
    )
    assert response.json()["data"]["items"] == [{"solicitud_id": 2}]


async def test_recurrences_count_buses_with_multiple_workshop_visits(dashboard_client, dashboard_data):
    now = datetime.now(timezone.utc)
    await dashboard_data.execute(update(V).where(V.c.id.in_([1, 2])).values(fecha_ingreso=now, fecha_salida=None))
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/buses/101/resumen")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["reincidencias"]["cantidad"] == 1

    # Dos visitas del mismo bus en distintos meses no forman reincidencia mensual.
    await dashboard_data.execute(update(V).where(V.c.id == 1).values(fecha_ingreso=now - timedelta(days=35), fecha_salida=None))
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/buses/101/resumen")
    assert response.json()["data"]["reincidencias"]["cantidad"] == 0
    response = await dashboard_client.get(f"{PREFIX}/indicadores?bus_id=101")
    assert response.json()["data"]["mensuales"]["reincidencias"] == 0
    await dashboard_data.execute(update(V).where(V.c.id == 1).values(fecha_ingreso=now, fecha_salida=now + timedelta(hours=1)))
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/buses/101/resumen")
    assert response.json()["data"]["reincidencias"]["cantidad"] == 1

    # Otra falla reportada no cambia cuántas visitas tuvo el bus.
    await dashboard_data.execute(update(D).where(D.c.solicitud_id == 2).values(
        descripcion_personalizada="Falla distinta", fecha_reporte=now - timedelta(days=60)
    ))
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/buses/101/resumen")
    assert response.json()["data"]["reincidencias"]["cantidad"] == 1

    # Una visita de una solicitud sin OT deja de contar como visita al taller.
    await dashboard_data.execute(update(S).where(S.c.id == 2).values(es_ot=False))
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/buses/101/resumen")
    assert response.json()["data"]["reincidencias"]["cantidad"] == 0


async def test_single_workshop_visit_is_not_recurrence(dashboard_client, dashboard_data):
    await dashboard_data.execute(update(S).where(S.c.id == 5).values(fecha_creacion=datetime.now(timezone.utc), fecha_cierre=datetime.now(timezone.utc) + timedelta(hours=1)))
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/buses/103/resumen")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["reincidencias"]["cantidad"] == 0


async def test_second_physical_entry_of_same_ot_counts_as_another_visit(dashboard_client, dashboard_data):
    now = datetime.now(timezone.utc)
    await dashboard_data.execute(update(V).where(V.c.id == 1).values(fecha_ingreso=now, fecha_salida=now + timedelta(hours=1)))
    await dashboard_data.execute(insert(V), {
        "id": 4, "solicitud_id": 1, "numero_visita": 2, "fecha_ingreso": now + timedelta(hours=2),
    })
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/reincidencias?bus_id=101")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"] == [{"bus_id": 101, "n_bus": "001", "visitas_mes": 2}]
    metrics = await dashboard_client.get(f"{PREFIX}/indicadores?bus_id=101")
    assert metrics.json()["data"]["mensuales"]["reincidencias"] == 1


async def test_legacy_state_history_counts_each_reentry_without_stadias(dashboard_client, dashboard_data):
    now = datetime.now(timezone.utc)
    await dashboard_data.execute(insert(SE), [
        {"id": 104, "solicitud_id": 5, "tipo_evento": "CAMBIO_ESTADO", "estado_anterior": "PENDIENTE", "estado_nuevo": "EN_REPARACION", "fecha_evento": now, "actor_nombre_snapshot": "Supervisor", "origen": "OPERACION"},
        {"id": 105, "solicitud_id": 5, "tipo_evento": "CAMBIO_ESTADO", "estado_anterior": "LIBERADO", "estado_nuevo": "EN_REPARACION", "fecha_evento": now + timedelta(hours=2), "actor_nombre_snapshot": "Supervisor", "origen": "OPERACION"},
    ])
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/reincidencias?bus_id=103")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"] == [{"bus_id": 103, "n_bus": "3", "visitas_mes": 2}]


async def test_age_group_boundaries(dashboard_data):
    from app.modules.dashboard.repository.dashboard_repository import DashboardRepository
    from sqlalchemy import union_all

    repository = DashboardRepository(dashboard_data)
    cutoff = await repository.age_cutoff()
    boundaries = [
        cutoff - timedelta(days=7),
        cutoff - timedelta(days=7, seconds=1),
        cutoff - timedelta(days=28),
        cutoff - timedelta(days=28, seconds=1),
    ]
    rows = union_all(*[select(literal(value).label("fecha_creacion")) for value in boundaries]).cte(
        "boundary_dates"
    )
    groups = (
        (await dashboard_data.execute(select(repository.queries.age_group(rows)))).scalars().all()
    )
    assert groups == ["HASTA_7_DIAS", "MAS_7_HASTA_28_DIAS", "MAS_7_HASTA_28_DIAS", "MAS_28_DIAS"]

@pytest.mark.parametrize("name,city,expected", [
    ("Externo", "Temuco", {1}),
    ("Externo", "Santiago", set()),
    ("Otro", "Temuco", set()),
])
async def test_external_workshop_drilldown(dashboard_client, dashboard_data, name, city, expected):
    response = await dashboard_client.get(f"{PREFIX}/solicitudes", params={
        "seleccion_tipo": "taller_externo",
        "seleccion_taller_nombre": name,
        "seleccion_taller_ciudad": city,
        "seleccion_periodos": "2026-10",
    })
    assert response.status_code == 200, response.text
    assert {item["id"] for item in response.json()["data"]["items"]} == expected


async def test_three_workshop_visits_same_bus_month_count_one_recurrent_bus(dashboard_client, dashboard_data):
    now = datetime.now(timezone.utc)
    await dashboard_data.execute(update(V).where(V.c.id == 3).values(fecha_ingreso=now, fecha_salida=None))
    await dashboard_data.execute(insert(V), [
        {"id": 4, "solicitud_id": 6, "numero_visita": 1, "fecha_ingreso": now},
        {"id": 5, "solicitud_id": 7, "numero_visita": 1, "fecha_ingreso": now},
    ])
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/buses/102/resumen")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["reincidencias"]["cantidad"] == 1
    response = await dashboard_client.get(f"{PREFIX}/indicadores?bus_id=102")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["mensuales"]["reincidencias"] == 1

async def test_recurrence_summary_matches_indicator(dashboard_client, dashboard_data):
    now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    await dashboard_data.execute(update(V).where(V.c.id == 3).values(fecha_ingreso=now, fecha_salida=None))
    await dashboard_data.execute(insert(V), [
        {"id": 4, "solicitud_id": 6, "numero_visita": 1, "fecha_ingreso": now},
        {"id": 5, "solicitud_id": 7, "numero_visita": 1, "fecha_ingreso": now},
    ])
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/reincidencias?bus_id=102&meses=11&anios=2026")
    assert response.status_code == 200, response.text
    page = response.json()["data"]
    assert page["total"] == 1
    assert page["items"][0]["bus_id"] == 102
    assert page["items"][0]["visitas_mes"] == 3
    metrics = await dashboard_client.get(f"{PREFIX}/indicadores?bus_id=102&meses=11&anios=2026")
    assert page["total"] == metrics.json()["data"]["mensuales"]["reincidencias"]
    outside = await dashboard_client.get(f"{PREFIX}/reincidencias?bus_id=102&meses=1&anios=2020")
    assert outside.json()["data"]["items"] == []
    response = await dashboard_client.get(f"{PREFIX}/reincidencias?bus_id=103")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"] == []

@pytest.mark.parametrize("kind,bus_filter", [("reincidencias_mes", {}), ("reincidencias_bus", {"seleccion_bus_id": 102})])
async def test_recurrence_selection_lists_only_requests_from_indicator_month(
    dashboard_client, dashboard_data, kind, bus_filter
):
    november = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    october = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    await dashboard_data.execute(update(S).where(S.c.id == 3).values(fecha_creacion=november))
    await dashboard_data.execute(update(S).where(S.c.id == 7).values(
        fecha_creacion=november, fecha_cierre=november + timedelta(hours=1)
    ))
    await dashboard_data.execute(update(S).where(S.c.id == 6).values(
        fecha_creacion=october, fecha_cierre=november + timedelta(hours=1)
    ))
    await dashboard_data.execute(update(V).where(V.c.id == 3).values(fecha_ingreso=november, fecha_salida=None))
    await dashboard_data.execute(insert(V), [
        {"id": 4, "solicitud_id": 6, "numero_visita": 1, "fecha_ingreso": november},
        {"id": 5, "solicitud_id": 7, "numero_visita": 1, "fecha_ingreso": november},
    ])
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/solicitudes", params={
        "seleccion_tipo": kind, "seleccion_periodo": "2026-11", **bus_filter,
    })
    assert response.status_code == 200, response.text
    assert {row["id"] for row in response.json()["data"]["items"]} == {3, 7}
