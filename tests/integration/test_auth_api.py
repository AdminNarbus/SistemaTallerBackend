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
    assert "refresh_token" in reg_data
    assert reg_data["user"]["username"] == "newuser"
    assert reg_data["user"]["rol"] == "CONDUCTOR"

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
    assert "refresh_token" in login_data

    # 3.1 Renovar el par de tokens sin volver a pedir credenciales
    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_data["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    assert "access_token" in refresh_response.json()
    assert "refresh_token" in refresh_response.json()

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


@pytest.mark.asyncio
async def test_supervisor_actualiza_usuario_parcialmente(client, auth_headers_supervisor, seed_test_data):
    """La edición personal es parcial y nunca borra valores con null o texto vacío."""
    usuario_id = seed_test_data["conductor"].id

    telefono = await client.patch(
        f"/api/v1/auth/usuarios/{usuario_id}",
        json={"telefono": "+56912345678"},
        headers=auth_headers_supervisor,
    )
    assert telefono.status_code == 200
    assert telefono.json()["telefono"] == "+56912345678"

    nombres = await client.patch(
        f"/api/v1/auth/usuarios/{usuario_id}",
        json={"nombre": "  Juan Actualizado  ", "apellido": "Conductor Nuevo"},
        headers=auth_headers_supervisor,
    )
    assert nombres.status_code == 200
    assert nombres.json()["nombre"] == "Juan Actualizado"
    assert nombres.json()["apellido"] == "Conductor Nuevo"
    assert nombres.json()["telefono"] == "+56912345678"

    conserva_null = await client.patch(
        f"/api/v1/auth/usuarios/{usuario_id}",
        json={"telefono": None},
        headers=auth_headers_supervisor,
    )
    assert conserva_null.status_code == 200
    assert conserva_null.json()["telefono"] == "+56912345678"

    conserva_vacio = await client.patch(
        f"/api/v1/auth/usuarios/{usuario_id}",
        json={"telefono": "   "},
        headers=auth_headers_supervisor,
    )
    assert conserva_vacio.status_code == 200
    assert conserva_vacio.json()["telefono"] == "+56912345678"

    no_modifica_restringidos = await client.patch(
        f"/api/v1/auth/usuarios/{usuario_id}",
        json={"rol": "ADMIN"},
        headers=auth_headers_supervisor,
    )
    assert no_modifica_restringidos.status_code == 422

    supervisor_id = seed_test_data["supervisor"].id
    actualiza_propio = await client.patch(
        f"/api/v1/auth/usuarios/{supervisor_id}",
        json={"telefono": "+56987654321"},
        headers=auth_headers_supervisor,
    )
    assert actualiza_propio.status_code == 200
    assert actualiza_propio.json()["telefono"] == "+56987654321"


@pytest.mark.asyncio
async def test_edicion_usuario_permisos_y_validaciones(
    client, auth_headers_conductor, auth_headers_supervisor, seed_test_data
):
    usuario_id = seed_test_data["conductor"].id

    forbidden = await client.patch(
        f"/api/v1/auth/usuarios/{usuario_id}",
        json={"telefono": "123"},
        headers=auth_headers_conductor,
    )
    assert forbidden.status_code == 403

    not_found = await client.patch(
        "/api/v1/auth/usuarios/99999",
        json={"telefono": "123"},
        headers=auth_headers_supervisor,
    )
    assert not_found.status_code == 404

    too_long = await client.patch(
        f"/api/v1/auth/usuarios/{usuario_id}",
        json={"telefono": "1" * 31},
        headers=auth_headers_supervisor,
    )
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_buscar_mecanicos_autocomplete(client, auth_headers_mecanico1, seed_test_data):
    """Prueba el buscador de mecánicos autocompletar en GET /api/v1/auth/mecanicos/buscar."""
    # 1. Búsqueda vacía -> lista todos los mecánicos activos
    res_all = await client.get("/api/v1/auth/mecanicos/buscar", headers=auth_headers_mecanico1)
    assert res_all.status_code == 200
    mecanicos = res_all.json()
    assert len(mecanicos) >= 2
    assert any(m["username"] == "mecanico1@narbus.cl" for m in mecanicos)

    # 2. Búsqueda por query string 'mecanico'
    res_q = await client.get("/api/v1/auth/mecanicos/buscar?q=mecanico", headers=auth_headers_mecanico1)
    assert res_q.status_code == 200
    assert len(res_q.json()) >= 1

    # 3. Alias /mecanicos
    res_alias = await client.get("/api/v1/auth/mecanicos?q=mecanico1", headers=auth_headers_mecanico1)
    assert res_alias.status_code == 200
    assert res_alias.json()[0]["username"] == "mecanico1@narbus.cl"
    assert "X-Total-Count" in res_alias.headers


@pytest.mark.asyncio
async def test_listar_usuarios_paginacion_y_filtros(client, auth_headers_supervisor, seed_test_data):
    """Prueba la paginación con default 20, cabecera X-Total-Count y filtros en GET /api/v1/auth/usuarios."""
    res = await client.get("/api/v1/auth/usuarios", headers=auth_headers_supervisor)
    assert res.status_code == 200
    assert "X-Total-Count" in res.headers
    total = int(res.headers["X-Total-Count"])
    assert total >= 4
    usuarios = res.json()
    assert len(usuarios) <= 20

    # Filtro por rol
    res_rol = await client.get("/api/v1/auth/usuarios?rol=MECANICO", headers=auth_headers_supervisor)
    assert res_rol.status_code == 200
    assert "X-Total-Count" in res_rol.headers
    for u in res_rol.json():
        assert u["rol"] == "MECANICO"

    # Filtro por término de búsqueda q
    res_q = await client.get("/api/v1/auth/usuarios?q=supervisor", headers=auth_headers_supervisor)
    assert res_q.status_code == 200
    assert len(res_q.json()) >= 1
    assert any("supervisor" in u["username"].lower() for u in res_q.json())


@pytest.mark.asyncio
async def test_supervision_usuarios_endpoint(client, auth_headers_supervisor, auth_headers_conductor):
    """Prueba el nuevo endpoint GET /api/v1/supervision/usuarios para la vista del supervisor."""
    # Conductor -> 403 Forbidden
    res_forbidden = await client.get("/api/v1/supervision/usuarios", headers=auth_headers_conductor)
    assert res_forbidden.status_code == 403

    # Supervisor -> 200 OK con cabecera X-Total-Count y paginación
    res_sup = await client.get("/api/v1/supervision/usuarios?skip=0&limit=20", headers=auth_headers_supervisor)
    assert res_sup.status_code == 200
    assert "X-Total-Count" in res_sup.headers
    assert int(res_sup.headers["X-Total-Count"]) >= 1
    assert len(res_sup.json()) <= 20
