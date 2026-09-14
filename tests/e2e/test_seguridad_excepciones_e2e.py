import pytest


@pytest.mark.asyncio
async def test_unauthorized_access_format(client):
    """Prueba que accesos sin autenticación devuelvan HTTP 401 con JSON estandarizado y header WWW-Authenticate."""
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert res.headers.get("WWW-Authenticate") == "Bearer"

    json_data = res.json()
    assert "error" in json_data
    assert json_data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_forbidden_access_format(client, auth_headers_conductor, seed_test_data):
    """Prueba que el rol insuficiente devuelva HTTP 403 con JSON estandarizado."""
    res = await client.get("/api/v1/supervision/auditoria/buses-taller", headers=auth_headers_conductor)
    assert res.status_code == 403
    json_data = res.json()
    assert json_data["error"]["code"] == "FORBIDDEN"
    assert "Acceso denegado" in json_data["error"]["message"]


@pytest.mark.asyncio
async def test_not_found_exception_format(client, auth_headers_mecanico1, seed_test_data):
    """Prueba que recursos inexistentes devuelvan HTTP 404 con error_code NOT_FOUND."""
    res = await client.get("/api/v1/mantencion/999999", headers=auth_headers_mecanico1)
    assert res.status_code == 404
    json_data = res.json()
    assert json_data["error"]["code"] == "NOT_FOUND"
    assert json_data["error"]["message"] == "Solicitud de taller no encontrada"


@pytest.mark.asyncio
async def test_business_rule_exception_format(client, auth_headers_conductor, auth_headers_mecanico1, seed_test_data):
    """Prueba que violaciones de reglas de negocio devuelvan HTTP 422 con error_code BUSINESS_RULE_VIOLATION."""
    # 1. Crear solicitud válida
    create_res = await client.post(
        "/api/v1/mantencion/solicitudes",
        json={"n_bus": "BUS-ERR", "descripcion_general": "Test error"},
        headers=auth_headers_conductor,
    )
    sol_id = create_res.json()["id"]

    # 2. Intentar desasignar a un mecánico que no está asignado
    res = await client.post(f"/api/v1/mantencion/{sol_id}/desasignarme", headers=auth_headers_mecanico1)
    assert res.status_code == 422
    json_data = res.json()
    assert json_data["error"]["code"] == "BUSINESS_RULE_VIOLATION"


@pytest.mark.asyncio
async def test_validation_error_format(client, auth_headers_conductor):
    """Prueba que errores de validación de Pydantic devuelvan HTTP 422 con error_code VALIDATION_ERROR."""
    res = await client.post(
        "/api/v1/mantencion/solicitudes",
        json={},  # n_bus obligatorio ausente
        headers=auth_headers_conductor,
    )
    assert res.status_code == 422
    json_data = res.json()
    assert json_data["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(json_data["error"]["detail"], list)
