import pytest
from sqlalchemy import event, update

from app.modules.dashboard.repository.relations import S

PREFIX = "/api/v1/dashboard"


@pytest.mark.parametrize(
    "path",
    [
        "indicadores",
        "series/tendencia",
        "series/antiguedad",
        "series/mecanicos",
        "series/buses-fallas",
        "series/buses-visitas",
        "series/talleres",
        "talleres/externos",
        "solicitudes",
        "filtros/buses",
        "filtros/solicitudes",
        "filtros/mecanicos",
        "filtros/periodos",
    ],
)
async def test_empty_collections_and_metrics(dashboard_client, path):
    response = await dashboard_client.get(f"{PREFIX}/{path}")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["metadata"]["fecha_referencia_datos"] is None


async def test_indicators_populations_dates_and_monthly(dashboard_client, dashboard_data):
    response = await dashboard_client.get(f"{PREFIX}/indicadores?meses=10&anios=2026")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["estados"] == {
        "total_ot": 6,
        "solicitadas_buses": 0,
        "pendientes_buses": 1,
        "en_reparacion_buses": 1,
        "liberados_buses": 0,
        "finalizadas_ot": 3,
        "reportadas_ot": 0,
    }
    assert data["tiempos"]["respuesta"]["validos"] == 0
    assert data["tiempos"]["respuesta"]["promedio_horas"] is None
    assert data["mensuales"]["ot_atendidas"] == 0
    assert data["mensuales"]["porcentaje_ot_atendidas"] is None


async def test_under_demand_reflects_committed_changes_without_writes(
    dashboard_client, dashboard_data
):
    before = (await dashboard_client.get(f"{PREFIX}/indicadores")).json()["data"]
    await dashboard_data.execute(update(S).where(S.c.id == 2).values(estado="LIBERADO"))
    await dashboard_data.commit()
    statements = []

    def capture(_conn, _cursor, statement, *_):
        statements.append(statement.lstrip().upper())

    event.listen(dashboard_data.bind.sync_engine, "before_cursor_execute", capture)
    try:
        response = await dashboard_client.get(f"{PREFIX}/indicadores")
    finally:
        event.remove(dashboard_data.bind.sync_engine, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    after = response.json()["data"]
    assert before["estados"]["pendientes_buses"] == 1
    assert after["estados"]["liberados_buses"] == 1
    assert all(sql.startswith(("SELECT", "WITH")) for sql in statements)


async def test_duration_uses_earliest_terminal_and_preserves_invalid(
    dashboard_client, dashboard_data
):
    response = await dashboard_client.get(f"{PREFIX}/solicitudes?solicitud_id=1")
    assert response.status_code == 200, response.text
    row = response.json()["data"]["items"][0]
    assert row["completo_horas"] == 37.0
    assert row["fecha_termino"].startswith("2026-10-02T12:00")
    times = (await dashboard_client.get(f"{PREFIX}/indicadores?solicitud_id=1")).json()["data"][
        "tiempos"
    ]
    assert times["respuesta"]["mediana_horas"] is None
    assert times["reparacion"]["promedio_horas"] == 23.0


@pytest.mark.parametrize(
    "name", ["tendencia", "antiguedad", "mecanicos", "buses-fallas", "buses-visitas", "talleres"]
)
async def test_all_series(dashboard_client, dashboard_data, name):
    response = await dashboard_client.get(f"{PREFIX}/series/{name}")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["serie"] == name
    assert response.headers["x-total-count"] == str(response.json()["data"]["total"])


async def test_mechanics_deduplicate_and_count_ot_only(dashboard_client, dashboard_data):
    response = await dashboard_client.get(f"{PREFIX}/series/mecanicos")
    assert response.status_code == 200, response.text
    points = {row["mecanico_id"]: row["fallas_unicas"] for row in response.json()["data"]["items"]}
    assert points == {1001: 2, 1002: 2}


async def test_latest_location_and_coverage(dashboard_client, dashboard_data):
    response = await dashboard_client.get(f"{PREFIX}/series/talleres")
    data = response.json()["data"]
    assert response.status_code == 200, response.text
    assert data["ot_clasificadas"] == 2
    assert data["ot_no_clasificables"] == 1
    assert data["ot_sin_ubicacion"] == 3
    assert {x["grupo"]: x["cantidad"] for x in data["items"]} == {
        "INTERNO_TEMUCO": 0,
        "INTERNO_SANTIAGO": 1,
        "EXTERNOS": 1,
    }
    response = await dashboard_client.get(
        f"{PREFIX}/solicitudes?seleccion_tipo=taller&seleccion_grupo=EXTERNOS"
    )
    assert [row["id"] for row in response.json()["data"]["items"]] == [1]


async def test_general_local_filters_and_pagination(dashboard_client, dashboard_data):
    response = await dashboard_client.get(
        f"{PREFIX}/solicitudes?meses=9&meses=10&estados=FINALIZADO&tabla_ot=1&limit=1&skip=0"
    )
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["data"]["items"]] == [1]
    assert response.json()["data"]["total"] == 1
    response = await dashboard_client.get(f"{PREFIX}/solicitudes?limit=1&skip=100")
    assert response.json()["data"]["items"] == []
    assert response.json()["data"]["total"] == 8


async def test_missing_bus_fk_unique_and_ambiguous(dashboard_client, dashboard_data):
    response = await dashboard_client.get(f"{PREFIX}/solicitudes")
    rows = {row["id"]: row for row in response.json()["data"]["items"]}
    assert rows[7]["bus_id"] == 102
    assert rows[8]["bus_id"] is None
    assert rows[4]["bus_id"] is None


async def test_recurrence_selection_includes_antecedent(dashboard_client, dashboard_data):
    response = await dashboard_client.get(
        f"{PREFIX}/solicitudes?seleccion_tipo=reincidencias_bus&seleccion_bus_id=101&seleccion_periodo=2026-10"
    )
    assert response.status_code == 200, response.text
    assert {row["id"] for row in response.json()["data"]["items"]} == {1, 2}


@pytest.mark.parametrize(
    "tail",
    [
        "resumen",
        "fallas?estado_falla=PENDIENTE",
        "fallas/solicitudes?estado_falla=PENDIENTE&descripcion=Freno%20no%20responde",
        "cronologia",
        "cronologia/detalles",
        "cronologia/resumen",
    ],
)
async def test_bus_endpoints(dashboard_client, dashboard_data, tail):
    response = await dashboard_client.get(f"{PREFIX}/buses/101/{tail}")
    assert response.status_code == 200, response.text


async def test_historical_fault_and_names_do_not_leak_into_past(dashboard_client, dashboard_data):
    response = await dashboard_client.get(
        f"{PREFIX}/buses/101/cronologia/detalles?hito_id=evento:100"
    )
    assert response.status_code == 200, response.text
    row = response.json()["data"]["items"][0]
    assert row["estado_falla"] == "PENDIENTE"
    assert row["mecanicos_nombres"] == []
    response = await dashboard_client.get(
        f"{PREFIX}/buses/101/cronologia/detalles?hito_id=evento:103"
    )
    row = response.json()["data"]["items"][0]
    assert row["estado_falla"] == "RESUELTA"
    assert row["mecanicos_nombres"] == ["Nombre histórico"]


async def test_export_summary_distinct_and_current_bus_unfiltered(dashboard_client, dashboard_data):
    response = await dashboard_client.get(
        f"{PREFIX}/buses/101/cronologia/resumen?hito_meses=9&hito_anios=2026"
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["estado_actual"] == "PENDIENTE"
    assert data["ot_distintas"] == 1
    assert data["fallas_distintas"] == 1
    assert data["pendientes"] == 1
    response = await dashboard_client.get(f"{PREFIX}/buses/101/cronologia/resumen")
    data = response.json()["data"]
    assert data["ot_distintas"] == 2
    assert data["fallas_distintas"] == 3
    assert data["resueltas"] == 1


async def test_no_orders_empty_stage_and_derived_milestones(dashboard_client, dashboard_data):
    response = await dashboard_client.get(f"{PREFIX}/buses/104/resumen")
    assert response.json()["data"]["estado"] is None
    response = await dashboard_client.get(f"{PREFIX}/buses/102/cronologia")
    assert response.status_code == 200, response.text
    assert any(row["derivado"] for row in response.json()["data"]["items"])


@pytest.mark.parametrize(
    "path",
    [
        "filtros/buses?contexto=maquina",
        "filtros/solicitudes?q=1",
        "filtros/mecanicos",
        "filtros/periodos?contexto=cronologia&bus_id=101",
        "talleres/externos",
    ],
)
async def test_options_and_privacy(dashboard_client, dashboard_data, path):
    response = await dashboard_client.get(f"{PREFIX}/{path}")
    assert response.status_code == 200, response.text
    assert not any(
        secret in response.text
        for secret in ("password_hash", "username", "telefono", "never-expose")
    )


@pytest.mark.parametrize(
    "path",
    [
        "indicadores?bus_id=101&n_bus=1",
        "indicadores?meses=13",
        "solicitudes?limit=101",
        "solicitudes?seleccion_tipo=taller",
        "solicitudes?seleccion_tipo=creadas&seleccion_semana=2026-10-20",
        "series/desconocida",
        "filtros/mecanicos?contexto=maquina",
    ],
)
async def test_invalid_input(dashboard_client, path):
    response = await dashboard_client.get(f"{PREFIX}/{path}")
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "path",
    [
        "buses/999/resumen",
        "buses/101/cronologia/detalles?hito_id=evento:999",
        "buses/102/cronologia/detalles?hito_id=evento:100",
    ],
)
async def test_not_found(dashboard_client, dashboard_data, path):
    response = await dashboard_client.get(f"{PREFIX}/{path}")
    assert response.status_code == 404, response.text
