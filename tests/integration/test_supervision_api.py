import pytest
import uuid
from datetime import datetime, timedelta, timezone
from app.modules.buses.models.bus import Bus
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_estadia import TallerSolicitudEstadia


def _parse_utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", ["RESUELTA", "INCOMPLETA", "PENDIENTE"])
@pytest.mark.parametrize("formato", ["json", "multipart"])
async def test_supervision_fecha_cambio_estado_json_y_multipart(
    client, auth_headers_supervisor, auth_headers_conductor, seed_test_data, estado, formato, taller_resultado
):
    mecanico = seed_test_data["mecanico1"]
    falla = seed_test_data["falla2"]
    solicitud_res = await client.post(
        "/api/v1/taller/solicitudes",
        json={
            "n_bus": f"BUS-FECHA-{uuid.uuid4().hex[:10]}",
            "descripcion_general": "Prueba de fecha de estado",
            "detalles": [{"categoria_id": falla.categoria_id, "descripcion_personalizada": "Prueba"}],
        },
        headers=auth_headers_conductor,
    )
    assert solicitud_res.status_code == 201
    solicitud = solicitud_res.json()
    detalle_id = solicitud["detalles"][0]["id"]
    fecha_elegida = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=10)
    iso = fecha_elegida.isoformat()
    payload = await taller_resultado["payload"](
        solicitud["id"], detalle_id, estado,
        [mecanico.id] if estado != "PENDIENTE" else None,
        fecha_cambio_estado=iso,
    )
    url = f"/api/v1/supervision/solicitudes/{solicitud['id']}/detalles/{detalle_id}/resolver"

    if formato == "json":
        response = await client.patch(url, json=payload, headers=auth_headers_supervisor)
    else:
        form_data = {key: [str(item) for item in value] if isinstance(value, list) else str(value)
                     for key, value in payload.items()}
        response = await client.patch(
            url,
            data=form_data,
            files={"fotos": ("evidencia.jpg", b"foto", "image/jpeg")},
            headers=auth_headers_supervisor,
        )

    assert response.status_code == 200, response.text
    actualizado = response.json()
    assert _parse_utc(actualizado["fecha_cambio_estado"]) == fecha_elegida
    fecha_registro_respuesta = _parse_utc(actualizado["fecha_registro"])
    assert fecha_registro_respuesta > fecha_elegida
    if estado == "RESUELTA":
        assert _parse_utc(actualizado["fecha_resolucion"]) == fecha_elegida
    else:
        assert actualizado["fecha_resolucion"] is None

    detalle_res = await client.get(
        f"/api/v1/supervision/solicitudes/{solicitud['id']}", headers=auth_headers_supervisor
    )
    detalle = detalle_res.json()["detalles"][0]
    assert _parse_utc(detalle["fecha_cambio_estado"]) == fecha_elegida
    ultimo_evento = detalle["historial_eventos"][-1]
    assert _parse_utc(ultimo_evento["fecha_evento"]) == fecha_elegida
    comentario_estado = next(
        comentario for comentario in detalle_res.json()["comentarios"]
        if comentario["tipo"] in {"RESOLUCION", "AVANCE", "REAPERTURA"}
        and comentario.get("fecha_evento") is not None
    )
    assert _parse_utc(comentario_estado["fecha_evento"]) == fecha_elegida
    fecha_registro = _parse_utc(comentario_estado["fecha_registro"])
    assert fecha_registro > fecha_elegida


@pytest.mark.asyncio
@pytest.mark.parametrize("formato", ["json", "multipart"])
async def test_supervision_fecha_cambio_estado_omitida_usa_hora_servidor(
    client, auth_headers_supervisor, auth_headers_conductor, seed_test_data, formato, taller_resultado
):
    mecanico = seed_test_data["mecanico1"]
    falla = seed_test_data["falla2"]
    solicitud_res = await client.post(
        "/api/v1/taller/solicitudes",
        json={
            "n_bus": f"BUS-SIN-FECHA-{uuid.uuid4().hex[:8]}",
            "descripcion_general": "Prueba fecha por defecto",
            "detalles": [{"categoria_id": falla.categoria_id, "descripcion_personalizada": "Prueba"}],
        },
        headers=auth_headers_conductor,
    )
    solicitud = solicitud_res.json()
    detalle_id = solicitud["detalles"][0]["id"]
    url = f"/api/v1/supervision/solicitudes/{solicitud['id']}/detalles/{detalle_id}/resolver"
    antes = datetime.now(timezone.utc)
    payload = await taller_resultado["payload"](solicitud["id"], detalle_id, "RESUELTA", [mecanico.id])
    if formato == "json":
        response = await client.patch(
            url,
            json=payload,
            headers=auth_headers_supervisor,
        )
    else:
        form_data = {key: [str(item) for item in value] if isinstance(value, list) else str(value)
                     for key, value in payload.items()}
        response = await client.patch(
            url,
            data=form_data,
            files={"fotos": ("evidencia.jpg", b"foto", "image/jpeg")},
            headers=auth_headers_supervisor,
        )
    despues = datetime.now(timezone.utc)
    assert response.status_code == 200, response.text
    fecha_aplicada = datetime.fromisoformat(response.json()["fecha_cambio_estado"].replace("Z", "+00:00"))
    assert antes <= fecha_aplicada <= despues


@pytest.mark.asyncio
async def test_supervision_resolucion_historica_anterior_a_creacion_ot(
    client, auth_headers_supervisor, auth_headers_conductor, seed_test_data, taller_resultado
):
    mecanico = seed_test_data["mecanico1"]
    solicitud_res = await client.post(
        "/api/v1/taller/solicitudes",
        json={
            "n_bus": f"BUS-RES-HIST-{uuid.uuid4().hex[:8]}",
            "detalles": [{"falla_id": seed_test_data["falla1"].id}],
        },
        headers=auth_headers_conductor,
    )
    assert solicitud_res.status_code == 201, solicitud_res.text
    solicitud = solicitud_res.json()
    detalle_id = solicitud["detalles"][0]["id"]
    fecha_creacion_ot = _parse_utc(solicitud["fecha_creacion"])
    fecha_resolucion = fecha_creacion_ot - timedelta(days=1)
    url = f"/api/v1/supervision/solicitudes/{solicitud['id']}/detalles/{detalle_id}/resolver"

    payload = await taller_resultado["payload"](
        solicitud["id"], detalle_id, "RESUELTA", [mecanico.id],
        fecha_cambio_estado=fecha_resolucion.isoformat(),
    )

    response = await client.patch(
        url,
        json=payload,
        headers=auth_headers_supervisor,
    )

    assert response.status_code == 200, response.text
    actualizado = response.json()
    assert actualizado["resuelto"] is True
    assert _parse_utc(actualizado["fecha_resolucion"]) == fecha_resolucion

    detalle_res = await client.get(
        f"/api/v1/supervision/solicitudes/{solicitud['id']}",
        headers=auth_headers_supervisor,
    )
    assert detalle_res.status_code == 200, detalle_res.text
    historial = detalle_res.json()["detalles"][0]["historial_eventos"]
    reportada = [evento for evento in historial if evento["tipo_evento"] == "REPORTADA"]
    resueltas = [evento for evento in historial if evento["tipo_evento"] == "RESUELTA"]
    assert len(reportada) == 1
    assert len(resueltas) == 1
    assert _parse_utc(resueltas[0]["fecha_evento"]) == fecha_resolucion



@pytest.mark.asyncio
async def test_multipart_resultado_acepta_talleres_colaboradores_repetidos(
    client, auth_headers_supervisor, auth_headers_conductor, seed_test_data, taller_resultado
):
    solicitud_res = await client.post(
        "/api/v1/taller/solicitudes",
        json={
            "n_bus": f"BUS-MULTIPART-{uuid.uuid4().hex[:8]}",
            "detalles": [{"falla_id": seed_test_data["falla1"].id}],
        },
        headers=auth_headers_conductor,
    )
    assert solicitud_res.status_code == 201, solicitud_res.text
    solicitud = solicitud_res.json()
    detalle_id = solicitud["detalles"][0]["id"]
    ciudades = await client.get("/api/v1/taller/ciudades", headers=auth_headers_supervisor)
    assert ciudades.status_code == 200, ciudades.text
    colaborador = await client.post(
        "/api/v1/taller/talleres",
        json={"nombre": "Colaborador externo", "ciudad_id": ciudades.json()[0]["id"], "tipo": "EXTERNO"},
        headers=auth_headers_supervisor,
    )
    assert colaborador.status_code == 201, colaborador.text
    payload = await taller_resultado["payload"](
        solicitud["id"], detalle_id, "RESUELTA", [seed_test_data["mecanico1"].id],
        talleres_colaboradores_ids=[colaborador.json()["id"]],
    )
    form_data = {
        key: [str(item) for item in value] if isinstance(value, list) else str(value)
        for key, value in payload.items()
    }
    response = await client.patch(
        f"/api/v1/supervision/solicitudes/{solicitud['id']}/detalles/{detalle_id}/resolver",
        data=form_data,
        files={"fotos": ("evidencia.jpg", b"foto", "image/jpeg")},
        headers=auth_headers_supervisor,
    )
    assert response.status_code == 200, response.text
    ubicacion = response.json()["ubicacion"]
    assert [item["id"] for item in ubicacion["talleres_colaboradores"]] == [colaborador.json()["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", ["PENDIENTE", "EN_REPARACION", "LIBERADO", "FINALIZADO"])
async def test_auditoria_envia_antiguedad_ot_y_ficha_tiempo_real(
    client, db_session, auth_headers_supervisor, seed_test_data, estado
):
    now = datetime.now(timezone.utc)
    solicitud = TallerSolicitud(
        es_ot=True,
        n_bus="SUP-EDAD-001", estado=estado,
        usuario_creador_id=seed_test_data["conductor"].id,
        fecha_creacion=now - timedelta(hours=72),
        fecha_cierre=now - timedelta(hours=1) if estado == "FINALIZADO" else None,
        horas_taller_acumuladas=0.0,
    )
    horas_reales = 0.0
    if estado != "PENDIENTE":
        abierta = estado == "EN_REPARACION"
        solicitud.fecha_primer_ingreso_taller = now - timedelta(hours=5)
        solicitud.estadias = [TallerSolicitudEstadia(
            numero_visita=1, fecha_ingreso=now - timedelta(hours=5),
            fecha_salida=None if abierta else now - timedelta(hours=4),
            horas_estadia=None if abierta else 1.0,
        )]
        horas_reales = 5.0 if abierta else 1.0
    db_session.add(solicitud)
    await db_session.commit()
    res = await client.get(
        "/api/v1/supervision/auditoria/buses-taller?skip=0&limit=20&_revalidar=1791561730993",
        headers=auth_headers_supervisor,
    )
    assert res.status_code == 200
    resumen = next(row for row in res.json() if row["id"] == solicitud.id)
    assert resumen["tiempo_taller"] == pytest.approx(72.0, abs=0.1)
    ficha = await client.get(f"/api/v1/taller/{solicitud.id}", headers=auth_headers_supervisor)
    assert ficha.status_code == 200
    assert ficha.json()["horas_en_taller"] == pytest.approx(horas_reales, abs=0.1)


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
        es_ot=True,
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
    """Prueba que el endpoint de auditoría retorne SolicitudResumenDTO con campos idénticos al mecánico."""
    res = await client.get("/api/v1/supervision/auditoria/buses-taller", headers=auth_headers_supervisor)
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    for sol in items:
        assert "id" in sol
        assert "estado" in sol
        assert "n_bus" in sol
        assert "fecha_ingreso" in sol
        assert "chofer" in sol
        assert "tiempo_taller" in sol
        assert "numero_fallas" in sol
        assert isinstance(sol["numero_fallas"], int)


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
    create_res = await client.post("/api/v1/taller/solicitudes", json=sol_payload, headers=auth_headers_conductor)
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
    assert any(c["comentario"].startswith("Nueva falla:") and "Rotor deformado" in c["comentario"] for c in comentarios)


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
    create_res = await client.post("/api/v1/taller/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    assert create_res.status_code == 201
    sol_id = create_res.json()["id"]

    # Supervisora agrega falla que ya fue solucionada por mecanico1
    aprobada = await client.post(f"/api/v1/taller/{sol_id}/aprobar", json={}, headers=auth_headers_supervisor)
    assert aprobada.status_code == 200, aprobada.text
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
    client, auth_headers_supervisor, auth_headers_conductor, seed_test_data, taller_resultado
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
    create_res = await client.post("/api/v1/taller/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    assert create_res.status_code == 201
    sol_data = create_res.json()
    sol_id = sol_data["id"]
    detalle_id = sol_data["detalles"][0]["id"]

    # 2. Supervisora intenta resolver sin mecanicos_ids explícito -> 422.
    sin_autores = await taller_resultado["payload"](sol_id, detalle_id, "RESUELTA", None)
    sin_autores.pop("mecanicos_ids")
    res_sin_mec = await client.patch(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles/{detalle_id}/resolver",
        json=sin_autores,
        headers=auth_headers_supervisor,
    )
    assert res_sin_mec.status_code == 422
    assert "mecanicos_ids explícitamente" in res_sin_mec.json()["error"]["message"]

    # 3. Supervisora resuelve la falla indicando qué mecánico la arregló
    payload_resolver = await taller_resultado["payload"](
        sol_id, detalle_id, "RESUELTA", [mecanico1.id],
        comentario="Se lubricó el vástago y se calibró la presión",
    )
    res_resolver = await client.patch(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles/{detalle_id}/resolver",
        json=payload_resolver,
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
    assert any(" reparó: " in c["comentario"] and mecanico1.nombre_completo in c["comentario"] for c in comentarios)

    # 5. Supervisora reabre la avería si se requiere nueva revisión
    payload_reabrir = await taller_resultado["payload"](
        sol_id, detalle_id, "PENDIENTE", comentario="Persiste leve pérdida de aire en prueba de ruta",
    )
    res_reabrir = await client.patch(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles/{detalle_id}/resolver",
        json=payload_reabrir,
        headers=auth_headers_supervisor,
    )
    assert res_reabrir.status_code == 200
    det_reabierto = res_reabrir.json()
    assert det_reabierto["resuelto"] is False
    assert det_reabierto["mecanico_resolvio_id"] is None

    # 6. Probar alias /check en mantención con el contrato de resultado.
    payload_mant_check = await taller_resultado["payload"](sol_id, detalle_id, "RESUELTA", [mecanico1.id])
    res_mant_check = await client.patch(
        f"/api/v1/taller/{sol_id}/detalles/{detalle_id}/check",
        json=payload_mant_check,
        headers=auth_headers_supervisor,
    )
    assert res_mant_check.status_code == 200
    assert res_mant_check.json()["resuelto"] is True
    assert res_mant_check.json()["mecanico_resolvio_id"] == mecanico1.id

    # 7. Body JSON en la ruta de mantención.
    payload_mant_body = await taller_resultado["payload"](sol_id, detalle_id, "RESUELTA", [mecanico1.id])
    res_mant_body = await client.patch(
        f"/api/v1/taller/{sol_id}/detalles/{detalle_id}/check",
        json=payload_mant_body,
        headers=auth_headers_supervisor,
    )
    assert res_mant_body.status_code == 200
    assert res_mant_body.json()["resuelto"] is True
    assert res_mant_body.json()["mecanico_resolvio_id"] == mecanico1.id

    # 8. Probar el alias /check del módulo de supervisión.
    payload_sup_check = await taller_resultado["payload"](sol_id, detalle_id, "RESUELTA", [mecanico1.id])
    res_sup_check = await client.patch(
        f"/api/v1/supervision/solicitudes/{sol_id}/detalles/{detalle_id}/check",
        json=payload_sup_check,
        headers=auth_headers_supervisor,
    )
    assert res_sup_check.status_code == 200
    assert res_sup_check.json()["resuelto"] is True
    assert res_sup_check.json()["mecanico_resolvio_id"] == mecanico1.id
    assert res_sup_check.json()["mecanico_resolvio_nombre"] == mecanico1.nombre_completo

    # 9. Verificar que GET /solicitudes/{id} retorne el detalle con mecanico_resolvio_id y mecanico_resolvio_nombre
    res_ot_final = await client.get(f"/api/v1/supervision/solicitudes/{sol_id}", headers=auth_headers_supervisor)
    assert res_ot_final.status_code == 200
    ot_final_data = res_ot_final.json()
    assert ot_final_data["detalles"][0]["resuelto"] is True
    assert ot_final_data["detalles"][0]["mecanico_resolvio_id"] == mecanico1.id
    assert ot_final_data["detalles"][0]["mecanico_resolvio_nombre"] == mecanico1.nombre_completo



