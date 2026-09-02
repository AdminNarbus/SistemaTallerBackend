import pytest
from app.modules.buses.models.bus import Bus


@pytest.mark.asyncio
async def test_buses_buscar_endpoint(client, db_session):
    """Prueba el endpoint GET /api/v1/buses/buscar?query={query}."""
    buses = [
        Bus(id=1, n_bus="10", patente="AA1010", marca="Mercedes", modelo="O500", is_active=True),
        Bus(id=2, n_bus="301", patente="BB3001", marca="Scania", modelo="K400", is_active=True),
        Bus(id=3, n_bus="339", patente="CC3399", marca="Volvo", modelo="B430", is_active=True),
        Bus(id=4, n_bus="342", patente="DD3422", marca="Scania", modelo="K440", is_active=True),
        Bus(id=5, n_bus="405", patente="EE4055", marca="Mercedes", modelo="O500", is_active=True),
    ]
    for b in buses:
        db_session.add(b)
    await db_session.commit()

    # Buscar prefijo "3"
    response = await client.get("/api/v1/buses/buscar?query=3")
    assert response.status_code == 200
    data = response.json()
    assert data == ["301", "339", "342"]

    # Buscar prefijo "33"
    response_33 = await client.get("/api/v1/buses/buscar?query=33")
    assert response_33.status_code == 200
    assert response_33.json() == ["339"]

    # Buscar sin query (todos)
    response_all = await client.get("/api/v1/buses/buscar")
    assert response_all.status_code == 200
    assert response_all.json() == ["10", "301", "339", "342", "405"]


@pytest.mark.asyncio
async def test_buses_get_por_id_y_numero_endpoint(client, db_session):
    """Prueba los endpoints de consulta de detalle GET /api/v1/buses/{id} y /numero/{n_bus}."""
    bus = Bus(id=7, n_bus="339", patente="GH3399", marca="Volvo", modelo="B430", is_active=True)
    db_session.add(bus)
    await db_session.commit()

    # Get por ID
    res_id = await client.get("/api/v1/buses/7")
    assert res_id.status_code == 200
    json_id = res_id.json()
    assert json_id["id"] == 7
    assert json_id["n_bus"] == "339"
    assert json_id["patente"] == "GH3399"

    # Get por n_bus
    res_num = await client.get("/api/v1/buses/numero/339")
    assert res_num.status_code == 200
    json_num = res_num.json()
    assert json_num["id"] == 7
    assert json_num["patente"] == "GH3399"

    # Inexistente
    res_not_found = await client.get("/api/v1/buses/999")
    assert res_not_found.status_code == 404
