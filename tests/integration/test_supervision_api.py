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


@pytest.mark.asyncio
async def test_supervision_agregar_falla_y_detalle_ot(
    client, auth_headers_supervisor, auth_headers_conductor, seed_test_data
):
    """Prueba que la supervisora pueda agregar una avería y consultar el detalle completo de la OT."""
    falla_frenos = seed_test_data["falla2"]

    # 1. Crear OT por conductor
    sol_payload = {
        "n_bus": "BUS-SUP-FALLAS",
        "descripcion_general": "Revisión técnica supervisada",
    }
    create_res = await client.post("/api/v1/mantencion/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    assert create_res.status_code == 201
    sol_id = create_res.json()["id"]

    # 2. Supervisora consulta detalle de la OT directamente vía /supervision/solicitudes/{id}
    res_detalle = await client.get(f"/api/v1/supervision/solicitudes/{sol_id}", headers=auth_headers_supervisor)
    assert res_detalle.status_code == 200
    assert res_detalle.json()["id"] == sol_id

    # 3. Conductor intenta agregar falla desde supervisión -> 403 Forbidden
    res_forbidden = await client.post(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles",
        json={"categoria_id": falla_frenos.categoria_id, "descripcion_personalizada": "Intento indebido"},
        headers=auth_headers_conductor,
    )
    assert res_forbidden.status_code == 403

    # 4. Supervisora agrega falla pendiente
    res_agrega = await client.post(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles",
        json={
            "categoria_id": falla_frenos.categoria_id,
            "descripcion_personalizada": "Rotor deformado detectado por supervisora",
        },
        headers=auth_headers_supervisor,
    )
    assert res_agrega.status_code == 201
    sol_actualizada = res_agrega.json()
    assert len(sol_actualizada["detalles"]) == 1
    det = sol_actualizada["detalles"][0]
    assert det["resuelto"] is False
    assert det["mecanico_resolvio_id"] is None
    assert "Rotor deformado" in det["descripcion_personalizada"]

    # Verificar que en la bitácora conste el registro de la supervisora
    comentarios = sol_actualizada["comentarios"]
    assert any("Supervisora" in c["comentario"] and "Rotor deformado" in c["comentario"] for c in comentarios)


@pytest.mark.asyncio
async def test_supervision_agregar_falla_resuelta_con_mecanico(
    client, auth_headers_supervisor, auth_headers_conductor, seed_test_data
):
    """Prueba que la supervisora pueda agregar una avería marcándola directamente como resuelta por un mecánico."""
    mecanico1 = seed_test_data["mecanico1"]
    falla_frenos = seed_test_data["falla2"]

    sol_payload = {
        "n_bus": "BUS-SUP-RESUELTA",
        "descripcion_general": "Inspección de egreso",
    }
    create_res = await client.post("/api/v1/mantencion/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    assert create_res.status_code == 201
    sol_id = create_res.json()["id"]

    # Supervisora agrega falla que ya fue solucionada por mecanico1
    res_agrega = await client.post(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles",
        json={
            "categoria_id": falla_frenos.categoria_id,
            "descripcion_personalizada": "Ajuste de freno de estacionamiento",
            "resuelto": True,
            "mecanico_resolvio_id": mecanico1.id,
        },
        headers=auth_headers_supervisor,
    )
    assert res_agrega.status_code == 201
    data = res_agrega.json()
    assert len(data["detalles"]) == 1
    det = data["detalles"][0]
    assert det["resuelto"] is True
    assert det["mecanico_resolvio_id"] == mecanico1.id


@pytest.mark.asyncio
async def test_supervision_resolver_falla_indicando_mecanico_flujo(
    client, auth_headers_supervisor, auth_headers_conductor, seed_test_data
):
    """Prueba completa para que la supervisora indique qué mecánico arregló una falla existente o la reabra."""
    mecanico1 = seed_test_data["mecanico1"]
    falla_frenos = seed_test_data["falla2"]

    # 1. Crear solicitud con 1 falla pendiente
    sol_payload = {
        "n_bus": "BUS-SUP-CHECK",
        "descripcion_general": "Falla pendiente para resolución",
        "detalles": [
            {
                "categoria_id": falla_frenos.categoria_id,
                "descripcion_personalizada": "Válvula de freno de mano trabada",
            }
        ],
    }
    create_res = await client.post("/api/v1/mantencion/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    assert create_res.status_code == 201
    sol_data = create_res.json()
    sol_id = sol_data["id"]
    detalle_id = sol_data["detalles"][0]["id"]

    # 2. Supervisora intenta resolver sin indicar mecanico_id -> 422 BusinessRuleException
    res_sin_mec = await client.patch(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles/{detalle_id}/resolver",
        json={"resuelto": True, "mecanico_id": None},
        headers=auth_headers_supervisor,
    )
    assert res_sin_mec.status_code == 422
    assert "Debe indicar el ID del mecánico" in res_sin_mec.json()["error"]["message"]

    # 3. Supervisora resuelve la falla indicando qué mecánico la arregló
    res_resolver = await client.patch(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles/{detalle_id}/resolver",
        json={
            "resuelto": True,
            "mecanico_id": mecanico1.id,
            "comentario": "Se lubricó el vástago y se calibró la presión",
        },
        headers=auth_headers_supervisor,
    )
    assert res_resolver.status_code == 200
    det_update = res_resolver.json()
    assert det_update["resuelto"] is True
    assert det_update["mecanico_resolvio_id"] == mecanico1.id
    assert det_update["mecanico_resolvio_nombre"] == mecanico1.nombre_completo

    # 4. Verificar que la OT refleje la resolución y el comentario en bitácora
    res_ot = await client.get(f"/api/v1/supervision/solicitudes/{sol_id}", headers=auth_headers_supervisor)
    assert res_ot.status_code == 200
    ot_data = res_ot.json()
    assert ot_data["detalles"][0]["resuelto"] is True
    assert ot_data["detalles"][0]["mecanico_resolvio_id"] == mecanico1.id
    # Bitácora contiene la autoría de la supervisora y el mecánico
    comentarios = ot_data["comentarios"]
    assert any("Supervisora" in c["comentario"] and mecanico1.nombre_completo in c["comentario"] for c in comentarios)

    # 5. Supervisora reabre la avería si se requiere nueva revisión
    res_reabrir = await client.patch(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles/{detalle_id}/resolver",
        json={
            "resuelto": False,
            "comentario": "Persiste leve pérdida de aire en prueba de ruta",
        },
        headers=auth_headers_supervisor,
    )
    assert res_reabrir.status_code == 200
    det_reabierto = res_reabrir.json()
    assert det_reabierto["resuelto"] is False
    assert det_reabierto["mecanico_resolvio_id"] is None

    # 6. Probar endpoint de mantención /detalles/{id}/check invocado por supervisora con mecanico_id
    res_mant_check = await client.patch(
        f"/api/v1/mantencion/{sol_id}/detalles/{detalle_id}/check?resuelto=true&mecanico_id={mecanico1.id}",
        headers=auth_headers_supervisor,
    )
    assert res_mant_check.status_code == 200
    assert res_mant_check.json()["resuelto"] is True
    assert res_mant_check.json()["mecanico_resolvio_id"] == mecanico1.id



