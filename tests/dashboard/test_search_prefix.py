from datetime import datetime

import pytest
from sqlalchemy import insert

from app.modules.dashboard.repository.relations import B, S


@pytest.fixture
async def prefix_orders(dashboard_data):
    await dashboard_data.execute(insert(B), [
        {"id": 201, "n_bus": "10", "patente": "PR-10", "is_active": True},
        {"id": 202, "n_bus": "123", "patente": "PR-123", "is_active": True},
        {"id": 203, "n_bus": "21", "patente": "PR-21", "is_active": True},
    ])
    await dashboard_data.execute(insert(S), [
        {"id": number, "bus_id": bus, "n_bus": n_bus, "estado": "FINALIZADO" if number == 315 else "PENDIENTE",
         "es_ot": True, "fecha_creacion": datetime(2026, 10, 20)}
        for number, bus, n_bus in ((10, 201, "10"), (123, 202, "123"), (21, 203, "21"), (315, 203, "21"))
    ])
    await dashboard_data.commit()


@pytest.mark.parametrize("query,expected", [
    ({"tabla_ot": "1"}, {1, 10, 123}),
    ({"tabla_ot": "# 1"}, {1, 10, 123}),
    ({"tabla_ot": "12"}, {123}),
    ({"tabla_ot": "%"}, set()),
    ({"tabla_n_bus": "1"}, {1, 2, 8, 10, 123}),
    ({"tabla_n_bus": "#001"}, {1, 2, 8, 10, 123}),
    ({"tabla_ot": "1", "tabla_n_bus": "12"}, {123}),
])
async def test_table_prefix_filters(dashboard_client, prefix_orders, query, expected):
    response = await dashboard_client.get("/api/v1/dashboard/solicitudes", params=query)

    assert response.status_code == 200, response.text
    page = response.json()["data"]
    assert {item["id"] for item in page["items"]} == expected
    assert page["total"] == len(expected)
    assert response.headers["X-Total-Count"] == str(len(expected))


async def test_prefix_pagination_and_autocomplete(dashboard_client, prefix_orders):
    response = await dashboard_client.get("/api/v1/dashboard/solicitudes", params={
        "tabla_ot": "1", "skip": 1, "limit": 1,
    })
    assert response.status_code == 200, response.text
    page = response.json()["data"]
    assert len(page["items"]) == 1
    assert page["total"] == 3
    options = await dashboard_client.get("/api/v1/dashboard/filtros/solicitudes", params={
        "q": "1", "contexto": "tabla",
    })
    assert options.status_code == 200, options.text
    assert {item["id"] for item in options.json()["data"]["items"]} == {1, 10, 123}
