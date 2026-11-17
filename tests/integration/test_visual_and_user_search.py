from importlib import import_module

import pytest

from app.modules.auth.rate_limit import AuthRateLimiter

@pytest.fixture
async def visual_headers(client, auth_headers_supervisor, monkeypatch):
    # Cada caso tiene su propia ventana; no consume el límite de otras pruebas.
    monkeypatch.setattr(import_module("app.modules.auth.api.router"), "auth_rate_limiter", AuthRateLimiter())
    response = await client.post(
        "/api/v1/auth/usuarios", headers=auth_headers_supervisor,
        json={"username": "consulta", "password": "1234", "rol": "VISUAL"},
    )
    assert response.status_code == 201, response.text
    login = await client.post(
        "/api/v1/auth/login", json={"username": "consulta", "password": "1234"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["rol"] == "VISUAL"
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.parametrize("path", [
    "/api/v1/auth/usuarios", "/api/v1/supervision/usuarios",
    "/api/v1/taller/pendientes", "/api/v1/taller/buses",
    "/api/v1/formularios/pauta/items", "/api/v1/auth/me",
])
async def test_visual_can_read(client, visual_headers, path):
    response = await client.get(path, headers=visual_headers)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/api/v1/auth/usuarios", {"username": "otro", "password": "1234"}),
    ("PATCH", "/api/v1/auth/usuarios/1", {"password": "9876"}),
    ("DELETE", "/api/v1/auth/usuarios/1", None),
    ("POST", "/api/v1/taller/solicitudes", {}),
    ("PATCH", "/api/v1/buses/1/en-taller", {"en_taller": True}),
    ("POST", "/api/v1/formularios/neumaticos", None),
    ("POST", "/api/v1/formularios/formularioNeumatico", None),
    ("POST", "/api/v1/auth/register", {"username": "otro", "password": "1234"}),
])
async def test_visual_cannot_write(client, visual_headers, method, path, payload):
    response = await client.request(method, path, headers=visual_headers, json=payload)
    assert response.status_code == 403, response.text
    assert "VISUAL" in response.text


async def test_visual_can_refresh(client, visual_headers):
    login = await client.post(
        "/api/v1/auth/login", headers=visual_headers,
        json={"username": "consulta", "password": "1234"},
    )
    response = await client.post(
        "/api/v1/auth/refresh", headers=visual_headers,
        json={"refresh_token": login.json()["refresh_token"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["rol"] == "VISUAL"


@pytest.mark.parametrize("path", [
    "/api/v1/auth/usuarios", "/api/v1/supervision/usuarios",
    "/api/v1/auth/mecanicos",
])
async def test_search_first_name_and_surname(
    client, db_session, seed_test_data, auth_headers_supervisor, path,
):
    user = seed_test_data["mecanico1"]
    user.nombre, user.apellido = "Juan Carlos", "Perez Soto"
    other = seed_test_data["mecanico2"]
    other.nombre, other.apellido = "Juan Antonio", "Gomez Soto"
    await db_session.commit()
    for query in ("Juan Perez", "  pErEz   jUaN  ", "Juan Carlos Perez Soto", "mecanico1@narbus.cl"):
        response = await client.get(path, headers=auth_headers_supervisor, params={"q": query})
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()] == [user.id]
        assert response.headers["X-Total-Count"] == "1"
    missing = await client.get(path, headers=auth_headers_supervisor, params={"q": "Juan Inexistente"})
    assert missing.json() == []
    assert missing.headers["X-Total-Count"] == "0"


async def test_search_filters_and_pagination(client, auth_headers_supervisor):
    path = "/api/v1/auth/usuarios"
    for name, active in (("Juan Carlos", True), ("Juan Andres", True), ("Juan Luis", False)):
        response = await client.post(path, headers=auth_headers_supervisor, json={
            "username": name.replace(" ", ""), "password": "1234", "nombre": name,
            "apellido": "Perez Soto", "rol": "VISUAL", "is_active": active,
        })
        assert response.status_code == 201, response.text
    response = await client.get(path, headers=auth_headers_supervisor, params={
        "q": "Juan Perez", "rol": "VISUAL", "is_active": True, "skip": 1, "limit": 1,
    })
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.headers["X-Total-Count"] == "2"


async def test_conductor_still_cannot_list_users(client, auth_headers_conductor):
    response = await client.get("/api/v1/auth/usuarios", headers=auth_headers_conductor)
    assert response.status_code == 403
