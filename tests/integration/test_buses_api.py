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
    assert "max-age" in response.headers.get("cache-control", "")
    data = response.json()
    assert [item["n_bus"] for item in data] == ["301", "339", "342"]
    assert data[0]["id"] == 2
    assert data[0]["patente"] == "BB3001"
    assert data[0]["en_taller"] is False

    # Buscar prefijo "33"
    response_33 = await client.get("/api/v1/buses/buscar?query=33")
    assert response_33.status_code == 200
    assert [item["n_bus"] for item in response_33.json()] == ["339"]

    # Buscar sin query (incluye todos los activos en catálogo)
    response_default = await client.get("/api/v1/buses/buscar")
    assert response_default.status_code == 200
    assert [item["n_bus"] for item in response_default.json()] == ["10", "301", "339", "342", "405"]

    # Buscar sin query con solo_flota_taller=false (incluye todos)
    response_all = await client.get("/api/v1/buses/buscar?solo_flota_taller=false")
    assert response_all.status_code == 200
    assert [item["n_bus"] for item in response_all.json()] == ["10", "301", "339", "342", "405"]



@pytest.mark.asyncio
async def test_buses_get_por_id_y_numero_endpoint(client, db_session):
    """Prueba los endpoints de consulta de detalle GET /api/v1/buses/{id} y /numero/{n_bus}."""
    bus = Bus(id=7, n_bus="339", patente="GH3399", marca="Volvo", modelo="B430", is_active=True, en_taller=False)
    db_session.add(bus)
    await db_session.commit()

    # Get por ID
    res_id = await client.get("/api/v1/buses/7")
    assert res_id.status_code == 200
    json_id = res_id.json()
    assert json_id["id"] == 7
    assert json_id["n_bus"] == "339"
    assert json_id["patente"] == "GH3399"
    assert json_id["en_taller"] is False

    # Get por n_bus
    res_num = await client.get("/api/v1/buses/numero/339")
    assert res_num.status_code == 200
    json_num = res_num.json()
    assert json_num["id"] == 7
    assert json_num["patente"] == "GH3399"

    # Inexistente
    res_not_found = await client.get("/api/v1/buses/999")
    assert res_not_found.status_code == 404


@pytest.mark.asyncio
async def test_actualizar_en_taller_endpoint(client, db_session, auth_headers_supervisor, auth_headers_conductor):
    """Prueba la actualización del estado en_taller mediante PATCH /api/v1/buses/{bus_id}/en-taller."""
    bus = Bus(id=8, n_bus="340", patente="IJ3400", marca="Scania", modelo="K400", is_active=True, en_taller=False)
    db_session.add(bus)
    await db_session.commit()

    payload = {"en_taller": True, "motivo": "Ingreso a taller por cambio de frenos"}

    # 1. Sin autenticación -> 401
    res_unauth = await client.patch("/api/v1/buses/8/en-taller", json=payload)
    assert res_unauth.status_code == 401

    # 2. Conductor (no supervisor) -> 403
    res_cond = await client.patch("/api/v1/buses/8/en-taller", json=payload, headers=auth_headers_conductor)
    assert res_cond.status_code == 403

    # 3. Supervisor -> 200 OK y en_taller pasa a True
    res_sup = await client.patch("/api/v1/buses/8/en-taller", json=payload, headers=auth_headers_supervisor)
    assert res_sup.status_code == 200
    data = res_sup.json()
    assert data["id"] == 8
    assert data["en_taller"] is True

    # 4. Bus inexistente con supervisor -> 404
    res_404 = await client.patch("/api/v1/buses/9999/en-taller", json=payload, headers=auth_headers_supervisor)
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_buses_listar_con_paginacion(client, db_session):
    """Prueba GET /api/v1/buses y /buscar con parámetros skip y limit."""
    buses = [
        Bus(id=20, n_bus="501", patente="PA5001", is_active=True, en_taller=False),
        Bus(id=21, n_bus="502", patente="PA5002", is_active=True, en_taller=False),
        Bus(id=22, n_bus="503", patente="PA5003", is_active=True, en_taller=False),
    ]
    for b in buses:
        db_session.add(b)
    await db_session.commit()

    # Listar con limit=2
    res = await client.get("/api/v1/buses?skip=0&limit=2")
    assert res.status_code == 200
    data = res.json()
    assert len(data) <= 2

    # Buscar con limit=1
    res_b = await client.get("/api/v1/buses/buscar?query=50&limit=1")
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert len(data_b) == 1
    assert data_b[0]["n_bus"] == "501"


@pytest.mark.asyncio
async def test_buses_crear_dar_de_baja_y_reactivar_endpoints(
    client, db_session, auth_headers_supervisor, auth_headers_conductor
):
    """Prueba POST /api/v1/buses, PATCH /{id}/dar-de-baja y PATCH /{id}/reactivar con RBAC."""
    payload = {
        "patente": "KKL-909",
        "n_bus": "909",
        "marca": "Scania",
        "modelo": "K360",
    }

    # 1. Sin auth -> 401
    res_unauth = await client.post("/api/v1/buses", json=payload)
    assert res_unauth.status_code == 401

    # 2. Conductor -> 403
    res_cond = await client.post("/api/v1/buses", json=payload, headers=auth_headers_conductor)
    assert res_cond.status_code == 403

    # 3. Supervisor -> 201 Created
    res_sup = await client.post("/api/v1/buses", json=payload, headers=auth_headers_supervisor)
    assert res_sup.status_code == 201
    bus_data = res_sup.json()
    assert bus_data["patente"] == "KKL-909"
    assert bus_data["n_bus"] == "909"
    assert bus_data["is_active"] is True
    assert bus_data["fecha_creacion"] is not None
    bus_id = bus_data["id"]

    # 4. Dar de baja con supervisor -> 200 OK
    payload_baja = {"motivo": "Fin de vida útil"}
    res_baja = await client.patch(
        f"/api/v1/buses/{bus_id}/dar-de-baja", json=payload_baja, headers=auth_headers_supervisor
    )
    assert res_baja.status_code == 200
    baja_data = res_baja.json()
    assert baja_data["is_active"] is False
    assert baja_data["motivo_baja"] == "Fin de vida útil"
    assert baja_data["fecha_baja"] is not None

    # 5. Reactivar con supervisor -> 200 OK
    res_reactivar = await client.patch(
        f"/api/v1/buses/{bus_id}/reactivar", headers=auth_headers_supervisor
    )
    assert res_reactivar.status_code == 200
    assert res_reactivar.json()["is_active"] is True


@pytest.mark.asyncio
async def test_supervision_buses_rutas_delegadas(client, db_session, auth_headers_supervisor):
    """Prueba endpoints delegados POST /api/v1/supervision/buses y PATCH /api/v1/supervision/buses/{id}/dar-de-baja."""
    payload = {"patente": "SUP-888", "n_bus": "888", "marca": "Volvo"}
    res = await client.post("/api/v1/supervision/buses", json=payload, headers=auth_headers_supervisor)
    assert res.status_code == 201
    bus_id = res.json()["id"]

    res_baja = await client.patch(
        f"/api/v1/supervision/buses/{bus_id}/dar-de-baja",
        json={"motivo": "Baja administrativa"},
        headers=auth_headers_supervisor,
    )
    assert res_baja.status_code == 200
    assert res_baja.json()["is_active"] is False



