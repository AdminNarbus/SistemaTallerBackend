import pytest


@pytest.mark.asyncio
async def test_auditoria_buses_taller_access_control(client, auth_headers_conductor, auth_headers_supervisor, seed_test_data):
    """Prueba la restricción de acceso al endpoint de auditoría de supervisión."""
    # 1. Sin autenticación -> 401
    res_unauth = await client.get("/api/v1/supervision/auditoria/buses-taller")
    assert res_unauth.status_code == 401

    # 2. Conductor (no supervisor) -> 403
    res_cond = await client.get("/api/v1/supervision/auditoria/buses-taller", headers=auth_headers_conductor)
    assert res_cond.status_code == 403

    # 3. Supervisor -> 200 OK
    res_sup = await client.get("/api/v1/supervision/auditoria/buses-taller", headers=auth_headers_supervisor)
    assert res_sup.status_code == 200
    assert isinstance(res_sup.json(), list)
