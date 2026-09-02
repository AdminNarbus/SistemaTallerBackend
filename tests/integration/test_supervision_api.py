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


@pytest.mark.asyncio
async def test_auditoria_buses_taller_filtros(client, auth_headers_supervisor, seed_test_data):
    """Prueba los filtros por n_bus, estado y mecanico_nombre en el endpoint de auditoría."""
    # Filtrar por bus 'BUS-101'
    res_bus = await client.get("/api/v1/supervision/auditoria/buses-taller?n_bus=BUS-101", headers=auth_headers_supervisor)
    assert res_bus.status_code == 200
    data_bus = res_bus.json()
    assert isinstance(data_bus, list)

    # Filtrar por estado 'REPORTADO'
    res_estado = await client.get("/api/v1/supervision/auditoria/buses-taller?estado=REPORTADO", headers=auth_headers_supervisor)
    assert res_estado.status_code == 200
    data_estado = res_estado.json()
    assert isinstance(data_estado, list)

    # Filtrar por nombre de mecánico 'Mecanico'
    res_mec = await client.get("/api/v1/supervision/auditoria/buses-taller?mecanico_nombre=Mecanico", headers=auth_headers_supervisor)
    assert res_mec.status_code == 200
    data_mec = res_mec.json()
    assert isinstance(data_mec, list)


@pytest.mark.asyncio
async def test_resumen_taller_kpis(client, auth_headers_conductor, auth_headers_supervisor, seed_test_data):
    """Prueba el endpoint de resumen general y KPIs del taller."""
    # 1. Conductor (no supervisor) -> 403
    res_cond = await client.get("/api/v1/supervision/resumen-taller", headers=auth_headers_conductor)
    assert res_cond.status_code == 403

    # 2. Supervisor -> 200 OK y estructura de métricas
    res_sup = await client.get("/api/v1/supervision/resumen-taller", headers=auth_headers_supervisor)
    assert res_sup.status_code == 200
    data = res_sup.json()
    assert "metricas_estado" in data
    assert "porcentaje_resolucion_fallas" in data
    assert "total_fallas_registradas" in data
    assert "total_fallas_resueltas" in data
    assert "fallas_por_categoria" in data
    assert "buses_activos_taller" in data
