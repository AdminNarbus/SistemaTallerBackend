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
