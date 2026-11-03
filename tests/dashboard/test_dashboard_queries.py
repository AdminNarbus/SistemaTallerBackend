from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, literal, select, update

from app.modules.dashboard.repository.relations import D, S
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


async def test_recurrence_window_includes_exactly_thirty_days(dashboard_client, dashboard_data):
    boundary = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    await dashboard_data.execute(update(D).where(D.c.id == 11).values(fecha_reporte=boundary - timedelta(days=30)))
    await dashboard_data.execute(update(D).where(D.c.id == 12).values(fecha_reporte=boundary))
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/buses/101/resumen")
    assert response.json()["data"]["reincidencias"]["cantidad"] == 1
    await dashboard_data.execute(
        update(D).where(D.c.id == 12).values(fecha_reporte=boundary + timedelta(seconds=1))
    )
    await dashboard_data.commit()
    response = await dashboard_client.get(f"{PREFIX}/buses/101/resumen")
    assert response.json()["data"]["reincidencias"]["cantidad"] == 0


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
