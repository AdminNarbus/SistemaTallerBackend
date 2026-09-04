import pytest


@pytest.mark.asyncio
async def test_get_catalogos_mantencion(client, auth_headers_mecanico1, seed_test_data):
    """Prueba la obtención de catálogos de categorías y fallas."""
    # Categorías
    res_cats = await client.get("/api/v1/mantencion/categorias", headers=auth_headers_mecanico1)
    assert res_cats.status_code == 200
    cats = res_cats.json()
    assert len(cats) >= 2

    # Fallas
    res_fallas = await client.get("/api/v1/mantencion/fallas", headers=auth_headers_mecanico1)
    assert res_fallas.status_code == 200
    fallas = res_fallas.json()
    assert len(fallas) >= 2


@pytest.mark.asyncio
async def test_mantencion_api_full_flow(client, auth_headers_conductor, auth_headers_mecanico1, seed_test_data):
    """Prueba la interacción HTTP completa en el módulo de mantención."""
    falla_id = seed_test_data["falla1"].id
    mecanico2_id = seed_test_data["mecanico2"].id

    # 1. Crear solicitud por conductor
    sol_payload = {
        "n_bus": "BUS-999",
        "descripcion_general": "Fuga leve de agua",
        "detalles": [{"falla_id": falla_id, "descripcion_personalizada": "En manguera superior"}],
    }
    create_res = await client.post("/api/v1/mantencion/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    assert create_res.status_code == 201
    sol_data = create_res.json()
    sol_id = sol_data["id"]
    detalle_id = sol_data["detalles"][0]["id"]
    assert sol_data["estado"] == "REPORTADO"

    # 2. Mecánico 1 revisa solicitudes pendientes
    pendientes_res = await client.get("/api/v1/mantencion/pendientes", headers=auth_headers_mecanico1)
    assert pendientes_res.status_code == 200
    pends = pendientes_res.json()
    assert any(p["id"] == sol_id for p in pends)

    # 3. Mecánico 1 toma la solicitud
    tomar_res = await client.post(
        f"/api/v1/mantencion/{sol_id}/tomar",
        json={"colaboradores_ids": [mecanico2_id], "comentario_inicial": "Revisando manguera"},
        headers=auth_headers_mecanico1,
    )
    assert tomar_res.status_code == 200
    assert tomar_res.json()["estado"] == "EN_REPARACION"

    # 4. Mecánico 1 revisa 'mis-trabajos'
    mis_trabajos_res = await client.get("/api/v1/mantencion/mis-trabajos", headers=auth_headers_mecanico1)
    assert mis_trabajos_res.status_code == 200
    assert any(m["id"] == sol_id for m in mis_trabajos_res.json())

    # 5. Check de falla resuelta
    check_res = await client.patch(
        f"/api/v1/mantencion/{sol_id}/detalles/{detalle_id}/check?resuelto=true",
        headers=auth_headers_mecanico1,
    )
    assert check_res.status_code == 200
    assert check_res.json()["detalles"][0]["resuelto"] is True

    # 6. Agregar comentario a la bitácora
    coment_res = await client.post(
        f"/api/v1/mantencion/{sol_id}/comentarios",
        json={"tipo": "GENERAL", "comentario": "Manguera reemplazada correctamente"},
        headers=auth_headers_mecanico1,
    )
    assert coment_res.status_code == 200
    assert len(coment_res.json()["comentarios"]) >= 2

    # 7. Finalizar la solicitud
    fin_res = await client.post(
        f"/api/v1/mantencion/{sol_id}/finalizar",
        json={"comentario_cierre": "Reparación concluida"},
        headers=auth_headers_mecanico1,
    )
    assert fin_res.status_code == 200
    assert fin_res.json()["estado"] == "FINALIZADO"


@pytest.mark.asyncio
async def test_tomar_trabajo_con_colaboradores_nombres(client, auth_headers_conductor, auth_headers_mecanico1, seed_test_data):
    """Prueba la asignación de colaboradores indicando sus nombres/usernames en lugar de IDs."""
    # 1. Crear solicitud por conductor
    sol_payload = {
        "n_bus": "BUS-777",
        "descripcion_general": "Revisión eléctrica",
    }
    create_res = await client.post("/api/v1/mantencion/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    assert create_res.status_code == 201
    sol_id = create_res.json()["id"]

    # 2. Mecánico 1 toma la solicitud enviando 'colaboradores_nombres'
    tomar_res = await client.post(
        f"/api/v1/mantencion/{sol_id}/tomar",
        json={
            "colaboradores_nombres": ["mecanico2@narbus.cl", "Mecanico Dos"],
            "comentario_inicial": "Iniciando trabajo en equipo por nombre"
        },
        headers=auth_headers_mecanico1,
    )
    assert tomar_res.status_code == 200
    data = tomar_res.json()
    assert data["estado"] == "EN_REPARACION"
    # Verificar que el colaborador fue asignado
    mecs = data["mecanicos"]
    assert len(mecs) >= 2
    assert any(m["mecanico_id"] == seed_test_data["mecanico2"].id for m in mecs)


@pytest.mark.asyncio
async def test_mecanico_agregar_falla_solicitud(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
    auth_headers_mecanico1,
):
    """Verifica que un mecánico pueda agregar una nueva avería a una solicitud existente."""
    cat_frenos_id = seed_test_data["falla2"].categoria_id
    mecanico1_id = seed_test_data["mecanico1"].id

    # 1. Conductor crea solicitud básica
    sol_payload = {
        "n_bus": "BUS-AGREGAR-FALLA",
        "descripcion_general": "Revisión general en taller",
    }
    create_res = await client.post("/api/v1/mantencion/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    assert create_res.status_code == 201
    sol_id = create_res.json()["id"]

    # 2. Conductor intenta agregar falla -> 403 Forbidden
    res_cond_forbidden = await client.post(
        f"/api/v1/mantencion/{sol_id}/detalles",
        json={"categoria_id": cat_frenos_id, "descripcion_personalizada": "Intento de chofer"},
        headers=auth_headers_conductor,
    )
    assert res_cond_forbidden.status_code == 403

    # 3. Mecánico agrega una falla con autoasignar=True (por defecto)
    res_mec_agrega = await client.post(
        f"/api/v1/mantencion/{sol_id}/detalles",
        json={
            "categoria_id": cat_frenos_id,
            "descripcion_personalizada": "Pastillas agrietadas detectadas durante la inspección",
            "autoasignar": True,
        },
        headers=auth_headers_mecanico1,
    )
    assert res_mec_agrega.status_code == 201
    data = res_mec_agrega.json()
    assert data["estado"] == "EN_REPARACION"
    assert len(data["detalles"]) == 1
    nueva_falla = data["detalles"][0]
    assert nueva_falla["categoria_id"] == cat_frenos_id
    assert nueva_falla["resuelto"] is False
    assert nueva_falla["descripcion_personalizada"] == "Pastillas agrietadas detectadas durante la inspección"
    assert len(nueva_falla["mecanicos_asignados"]) == 1
    assert nueva_falla["mecanicos_asignados"][0]["id"] == mecanico1_id

    # Verificar que en comentarios de bitácora quedó registrada la detección
    assert any("detectó y agregó una nueva avería" in c["comentario"] for c in data["comentarios"])


@pytest.mark.asyncio
async def test_agregar_falla_solicitud_finalizada_rechazo(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
    auth_headers_mecanico1,
):
    """Verifica que no se pueda agregar fallas a una solicitud que ya está FINALIZADA."""
    # 1. Crear solicitud
    sol_payload = {"n_bus": "BUS-FIN-RECHAZO"}
    create_res = await client.post("/api/v1/mantencion/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    sol_id = create_res.json()["id"]

    # 2. Finalizar solicitud
    fin_res = await client.post(
        f"/api/v1/mantencion/{sol_id}/finalizar",
        json={"motivo_incompleto_checklist": "No aplica pauta", "liberar_bus_taller": False},
        headers=auth_headers_mecanico1,
    )
    assert fin_res.status_code == 200
    assert fin_res.json()["estado"] == "FINALIZADO"

    # 3. Intentar agregar falla a la solicitud finalizada -> 422 BusinessRuleException
    add_res = await client.post(
        f"/api/v1/mantencion/{sol_id}/detalles",
        json={"categoria_id": 1, "descripcion_personalizada": "Falla tardía"},
        headers=auth_headers_mecanico1,
    )
    assert add_res.status_code == 422
    assert "no se pueden agregar fallas a una solicitud que ya ha sido finalizada" in add_res.json()["error"]["message"].lower()
