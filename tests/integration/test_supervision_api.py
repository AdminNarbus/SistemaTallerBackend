import pytest
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud


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


@pytest.mark.asyncio
async def test_auditoria_buses_taller_paginacion(client, auth_headers_supervisor, seed_test_data):
    """Prueba que el endpoint de auditoría responda correctamente con parámetros de paginación skip y limit."""
    res_page1 = await client.get("/api/v1/supervision/auditoria/buses-taller?skip=0&limit=1", headers=auth_headers_supervisor)
    assert res_page1.status_code == 200
    assert "X-Total-Count" in res_page1.headers
    data_page1 = res_page1.json()
    assert isinstance(data_page1, list)
    assert len(data_page1) <= 1

    res_page2 = await client.get("/api/v1/supervision/auditoria/buses-taller?skip=1&limit=1", headers=auth_headers_supervisor)
    assert res_page2.status_code == 200
    assert "X-Total-Count" in res_page2.headers
    data_page2 = res_page2.json()
    assert isinstance(data_page2, list)


@pytest.mark.asyncio
async def test_supervision_cambiar_estado_solicitud_flujo(
    client, db_session, auth_headers_supervisor, auth_headers_conductor, seed_test_data
):
    """Prueba completa del endpoint PATCH /api/v1/supervision/solicitudes/{id}/estado con RBAC y transiciones."""
    conductor = seed_test_data["conductor"]

    # 1. Sembrar bus y OT inicial
    bus = Bus(id=50, n_bus="705", patente="PLOP-75", is_active=True, en_taller=True)
    db_session.add(bus)
    await db_session.flush()

    ot = TallerSolicitud(
        id=901,
        n_bus="705",
        usuario_creador_id=conductor.id,
        estado="REPORTADO",
        descripcion_general="Falla de compresor de aire",
    )
    db_session.add(ot)
    await db_session.commit()

    payload_valido = {
        "estado": "PENDIENTE",
        "comentario": "Se asignará a turno tarde",
    }

    # 2. Sin autenticación -> 401
    res_unauth = await client.patch("/api/v1/supervision/solicitudes/901/estado", json=payload_valido)
    assert res_unauth.status_code == 401

    # 3. Conductor (no supervisor/admin) -> 403
    res_cond = await client.patch(
        "/api/v1/supervision/solicitudes/901/estado",
        json=payload_valido,
        headers=auth_headers_conductor,
    )
    assert res_cond.status_code == 403

    # 4. Solicitud inexistente -> 404
    res_404 = await client.patch(
        "/api/v1/supervision/solicitudes/99999/estado",
        json=payload_valido,
        headers=auth_headers_supervisor,
    )
    assert res_404.status_code == 404

    # 5. Transición exitosa REPORTADO -> PENDIENTE
    res_ok = await client.patch(
        "/api/v1/supervision/solicitudes/901/estado",
        json=payload_valido,
        headers=auth_headers_supervisor,
    )
    assert res_ok.status_code == 200
    data_ok = res_ok.json()
    assert data_ok["id"] == 901
    assert data_ok["estado"] == "PENDIENTE"
    assert any("Se asignará a turno tarde" in c["comentario"] for c in data_ok["comentarios"])

    # 6. Intentar cambiar al mismo estado -> 422 BusinessRuleException
    res_same = await client.patch(
        "/api/v1/supervision/solicitudes/901/estado",
        json={"estado": "PENDIENTE"},
        headers=auth_headers_supervisor,
    )
    assert res_same.status_code == 422

    # 7. Cambiar a FINALIZADO con liberar_bus_taller=True
    res_fin = await client.patch(
        "/api/v1/supervision/solicitudes/901/estado",
        json={
            "estado": "FINALIZADO",
            "comentario": "Reparación concluida y verificada",
            "liberar_bus_taller": True,
        },
        headers=auth_headers_supervisor,
    )
    assert res_fin.status_code == 200
    data_fin = res_fin.json()
    assert data_fin["estado"] == "FINALIZADO"
    assert data_fin["fecha_cierre"] is not None

    # 8. Reabrir solicitud FINALIZADO -> EN_REPARACION
    res_reopen = await client.patch(
        "/api/v1/supervision/solicitudes/901/estado",
        json={
            "estado": "EN_REPARACION",
            "comentario": "Reapertura por observación en prueba de ruta",
        },
        headers=auth_headers_supervisor,
    )
    assert res_reopen.status_code == 200
    data_reopen = res_reopen.json()
    assert data_reopen["estado"] == "EN_REPARACION"
    assert data_reopen["fecha_cierre"] is None


@pytest.mark.asyncio
async def test_supervision_mecanicos_carga_access_control(client, auth_headers_conductor, auth_headers_supervisor, seed_test_data):
    """Prueba RBAC y contrato DTO de GET /api/v1/supervision/mecanicos/carga."""
    # 1. Sin autenticación -> 401
    res_unauth = await client.get("/api/v1/supervision/mecanicos/carga")
    assert res_unauth.status_code == 401

    # 2. Conductor (no supervisor/admin) -> 403
    res_cond = await client.get("/api/v1/supervision/mecanicos/carga", headers=auth_headers_conductor)
    assert res_cond.status_code == 403

    # 3. Supervisor -> 200 OK con estructura MecanicoCargaDTO
    res_sup = await client.get("/api/v1/supervision/mecanicos/carga", headers=auth_headers_supervisor)
    assert res_sup.status_code == 200
    mecanicos = res_sup.json()
    assert isinstance(mecanicos, list)
    assert len(mecanicos) >= 1
    for m in mecanicos:
        assert "id" in m
        assert "nombre_completo" in m
        assert "username" in m
        assert "fallas_activas_count" in m
        assert isinstance(m["fallas_activas_count"], int)
        assert "disponible" in m
        assert isinstance(m["disponible"], bool)


@pytest.mark.asyncio
async def test_supervision_auditoria_campos_operacionales(client, auth_headers_supervisor, seed_test_data):
    """Prueba que el endpoint de auditoría incluya horas_en_taller, reincidencias_30d y fecha_liberacion."""
    res = await client.get("/api/v1/supervision/auditoria/buses-taller", headers=auth_headers_supervisor)
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    for sol in items:
        assert "horas_en_taller" in sol
        assert "reincidencias_30d" in sol
        assert "fecha_liberacion" in sol


