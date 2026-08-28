import pytest


@pytest.mark.asyncio
async def test_register_and_login_flow(client):
    """Prueba el registro y posterior login vía JSON y Form Data."""
    register_payload = {
        "nombre": "Nuevo",
        "apellido": "Usuario",
        "username": "newuser",
        "password": "password123",
        "rol": "MECANICO",
    }

    # 1. Registro
    reg_response = await client.post("/api/v1/auth/register", json=register_payload)
    assert reg_response.status_code == 201
    reg_data = reg_response.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["username"] == "newuser"

    # 2. Intentar registrar usuario duplicado (ConflictException -> 409)
    dup_response = await client.post("/api/v1/auth/register", json=register_payload)
    assert dup_response.status_code == 409
    assert dup_response.json()["error"]["code"] == "CONFLICT"

    # 3. Login JSON
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": "newuser", "password": "password123"},
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert "access_token" in login_data

    # 4. Login OAuth2 Form
    form_response = await client.post(
        "/api/v1/auth/login/token",
        data={"username": "newuser", "password": "password123"},
    )
    assert form_response.status_code == 200
    assert "access_token" in form_response.json()


@pytest.mark.asyncio
async def test_login_invalid_credentials(client, seed_test_data):
    """Prueba el rechazo con 401 para credenciales inválidas."""
    res = await client.post(
        "/api/v1/auth/login",
        json={"username": "conductor@narbus.cl", "password": "wrongpassword"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_me_endpoint(client, auth_headers_conductor, seed_test_data):
    """Prueba la obtención de la información del perfil logueado en GET /me."""
    res = await client.get("/api/v1/auth/me", headers=auth_headers_conductor)
    assert res.status_code == 200
    user_data = res.json()
    assert user_data["id"] == seed_test_data["conductor"].id


@pytest.mark.asyncio
async def test_usuarios_rbac_permissions(client, auth_headers_conductor, auth_headers_supervisor, seed_test_data):
    """Prueba los controles de acceso por rol (RBAC) en la gestión de usuarios."""
    # 1. Conductor intenta listar usuarios -> 403 Forbidden
    res_cond = await client.get("/api/v1/auth/usuarios", headers=auth_headers_conductor)
    assert res_cond.status_code == 403

    # 2. Supervisor lista usuarios -> 200 OK
    res_sup = await client.get("/api/v1/auth/usuarios", headers=auth_headers_supervisor)
    assert res_sup.status_code == 200
    assert isinstance(res_sup.json(), list)

    # 3. Soft delete por supervisor
    target_user_id = seed_test_data["conductor"].id
    del_res = await client.delete(f"/api/v1/auth/usuarios/{target_user_id}", headers=auth_headers_supervisor)
    assert del_res.status_code == 200
    assert del_res.json()["is_active"] is False

    # 4. Intentar deshabilitarse a sí mismo -> 400 Bad Request
    sup_id = seed_test_data["supervisor"].id
    self_del = await client.delete(f"/api/v1/auth/usuarios/{sup_id}", headers=auth_headers_supervisor)
    assert self_del.status_code == 400
