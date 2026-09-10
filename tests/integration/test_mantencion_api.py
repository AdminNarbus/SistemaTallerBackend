import io
import pytest


@pytest.mark.asyncio
async def test_get_catalogos_mantencion(client, auth_headers_mecanico1, seed_test_data):
    """Prueba la obtención de catálogos de categorías y fallas."""
    # Categorías
    res_cats = await client.get("/api/v1/mantencion/categorias", headers=auth_headers_mecanico1)
    assert res_cats.status_code == 200
    assert "max-age" in res_cats.headers.get("cache-control", "")
    cats = res_cats.json()
    assert len(cats) >= 2
    assert any(c.get("falla_id") is not None for c in cats)
    assert any(c.get("falla_nombre") is not None for c in cats)

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

    # 5. Check de falla resuelta — responde DetalleUpdateDTO (Nivel 3)
    check_res = await client.patch(
        f"/api/v1/mantencion/{sol_id}/detalles/{detalle_id}/check?resuelto=true",
        headers=auth_headers_mecanico1,
    )
    assert check_res.status_code == 200
    check_data = check_res.json()
    assert check_data["resuelto"] is True
    assert check_data["detalle_id"] == detalle_id

    # 6. Agregar comentario a la bitácora — responde ComentarioAddedDTO (Nivel 3)
    coment_res = await client.post(
        f"/api/v1/mantencion/{sol_id}/comentarios",
        json={"tipo": "GENERAL", "comentario": "Manguera reemplazada correctamente"},
        headers=auth_headers_mecanico1,
    )
    assert coment_res.status_code == 200
    coment_data = coment_res.json()
    assert coment_data["tipo"] == "GENERAL"
    assert coment_data["comentario"] == "Manguera reemplazada correctamente"
    assert "comentario_id" in coment_data

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


@pytest.mark.asyncio
async def test_create_solicitud_optimizada_con_bus_id_y_falla_id(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
):
    """Verifica que enviar bus_id y falla_id cree la solicitud de forma directa y óptima."""
    from app.modules.buses.models.bus import Bus
    bus = Bus(id=88, n_bus="339", patente="CC3399", is_active=True)
    db_session.add(bus)
    await db_session.commit()

    falla_id = seed_test_data["falla1"].id

    payload = {
        "bus_id": 88,
        "n_bus": "339",
        "bus_patente": "CC3399",
        "descripcion_general": "Falla óptima enviada con IDs numéricos",
        "detalles": [
            {
                "falla_id": falla_id,
                "categoria_id": 1,
                "falla_nombre": "Fuga de refrigerante",
                "descripcion_personalizada": "En radiador",
            }
        ],
    }
    res = await client.post("/api/v1/mantencion/solicitudes", json=payload, headers=auth_headers_conductor)
    assert res.status_code == 201
    data = res.json()
    assert data["bus_id"] == 88
    assert data["detalles"][0]["falla_id"] == falla_id
    assert data["detalles"][0]["falla"]["nombre"] == "Fuga de refrigerante"


@pytest.mark.asyncio
async def test_paginacion_pendientes_y_mis_trabajos(client, auth_headers_mecanico1, seed_test_data):
    """Verifica que los endpoints /pendientes y /mis-trabajos soporten paginación con skip y limit."""
    res_pends = await client.get("/api/v1/mantencion/pendientes?skip=0&limit=1", headers=auth_headers_mecanico1)
    assert res_pends.status_code == 200
    data_pends = res_pends.json()
    assert isinstance(data_pends, list)
    assert len(data_pends) <= 1

    res_trabajos = await client.get("/api/v1/mantencion/mis-trabajos?skip=0&limit=1", headers=auth_headers_mecanico1)
    assert res_trabajos.status_code == 200
    data_trabajos = res_trabajos.json()
    assert isinstance(data_trabajos, list)
    assert len(data_trabajos) <= 1


@pytest.mark.asyncio
async def test_crear_solicitud_con_foto_multipart(client, auth_headers_conductor, seed_test_data):
    """Verifica que POST /solicitudes admita multipart/form-data con archivo fotográfico en 1 solo request (retrocompatibilidad)."""
    fake_jpg = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"narbus_foto_solicitud"
    data = {
        "n_bus": "330",
        "descripcion_general": "Falla reportada con foto adjunta en 1 solo request",
    }
    files = {
        "foto": ("falla_motor.jpg", io.BytesIO(fake_jpg), "image/jpeg")
    }

    res = await client.post(
        "/api/v1/mantencion/solicitudes",
        data=data,
        files=files,
        headers=auth_headers_conductor,
    )
    assert res.status_code == 201
    res_data = res.json()
    assert res_data["n_bus"] == "330"
    assert res_data["foto_url"] is not None
    assert ("uploads/solicitudes" in res_data["foto_url"] or "storage.googleapis.com" in res_data["foto_url"])
    assert "evidencias" in res_data
    assert len(res_data["evidencias"]) == 1
    assert res_data["evidencias"][0]["url"] == res_data["foto_url"]
    assert res_data["evidencias"][0]["original_filename"] == "falla_motor.jpg"


@pytest.mark.asyncio
async def test_crear_solicitud_con_multiples_fotos_multipart(client, auth_headers_conductor, seed_test_data):
    """Verifica que un conductor pueda enviar múltiples imágenes de evidencia en una sola solicitud."""
    fake_jpg1 = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"foto_1_rueda"
    fake_jpg2 = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"foto_2_freno"
    fake_jpg3 = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"foto_3_motor"

    data = {
        "n_bus": "339",
        "descripcion_general": "Múltiples averías detectadas en ruta",
    }
    # En multipart HTTP se pueden enviar múltiples campos con el mismo nombre ('fotos')
    files = [
        ("fotos", ("evidencia_rueda.jpg", io.BytesIO(fake_jpg1), "image/jpeg")),
        ("fotos", ("evidencia_freno.jpg", io.BytesIO(fake_jpg2), "image/jpeg")),
        ("fotos", ("evidencia_motor.jpg", io.BytesIO(fake_jpg3), "image/jpeg")),
    ]

    res = await client.post(
        "/api/v1/mantencion/solicitudes",
        data=data,
        files=files,
        headers=auth_headers_conductor,
    )
    assert res.status_code == 201
    res_data = res.json()
    assert res_data["n_bus"] == "339"
    # foto_url principal asignada a la primera foto
    assert res_data["foto_url"] is not None
    assert len(res_data["evidencias"]) == 3
    assert res_data["foto_url"] == res_data["evidencias"][0]["url"]

    filenames = [ev["original_filename"] for ev in res_data["evidencias"]]
    assert "evidencia_rueda.jpg" in filenames
    assert "evidencia_freno.jpg" in filenames
    assert "evidencia_motor.jpg" in filenames


@pytest.mark.asyncio
async def test_crear_solicitud_con_fotos_urls_json(client, auth_headers_conductor, seed_test_data):
    """Verifica creación de solicitud vía JSON estándar con múltiples URLs en fotos_urls."""
    payload = {
        "n_bus": "339",
        "descripcion_general": "Reporte con múltiples URLs ya subidas",
        "fotos_urls": [
            "https://storage.googleapis.com/narbus-taller-media/solicitudes/img1.jpg",
            "https://storage.googleapis.com/narbus-taller-media/solicitudes/img2.jpg",
        ],
    }
    res = await client.post(
        "/api/v1/mantencion/solicitudes",
        json=payload,
        headers=auth_headers_conductor,
    )
    assert res.status_code == 201
    res_data = res.json()
    assert res_data["foto_url"] == "https://storage.googleapis.com/narbus-taller-media/solicitudes/img1.jpg"
    assert len(res_data["evidencias"]) == 2
    assert res_data["evidencias"][0]["url"] == "https://storage.googleapis.com/narbus-taller-media/solicitudes/img1.jpg"
    assert res_data["evidencias"][1]["url"] == "https://storage.googleapis.com/narbus-taller-media/solicitudes/img2.jpg"

