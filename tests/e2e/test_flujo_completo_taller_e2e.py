import pytest


@pytest.mark.asyncio
async def test_flujo_completo_taller_e2e(
    client,
    auth_headers_conductor,
    auth_headers_mecanico1,
    auth_headers_mecanico2,
    auth_headers_supervisor,
    seed_test_data,
):
    """
    PRUEBA DE SISTEMA / END-TO-END (E2E):
    Simula todo el ciclo de vida de una orden de taller con interacción de 4 usuarios:
    Conductor -> Mecánico Líder 1 -> Mecánico Colaborador 2 -> Supervisor Auditor.
    """
    conductor_id = seed_test_data["conductor"].id
    mecanico1_id = seed_test_data["mecanico1"].id
    mecanico2_id = seed_test_data["mecanico2"].id
    falla1_id = seed_test_data["falla1"].id
    falla2_id = seed_test_data["falla2"].id

    # -------------------------------------------------------------------------
    # PASO 1: Conductor reporta fallas en bus 'BUS-808'
    # -------------------------------------------------------------------------
    sol_payload = {
        "n_bus": "BUS-808",
        "descripcion_general": "Fuga de líquido y pastillas chillando",
        "detalles": [
            {"falla_id": falla1_id, "descripcion_personalizada": "Goteo visible en el piso"},
            {"falla_id": falla2_id, "descripcion_personalizada": "Sonido metálico al frenar"},
        ],
    }
    res_crear = await client.post("/api/v1/mantencion/solicitudes", json=sol_payload, headers=auth_headers_conductor)
    assert res_crear.status_code == 201
    sol_data = res_crear.json()
    sol_id = sol_data["id"]
    detalles = sol_data["detalles"]
    det1_id = detalles[0]["id"]
    det2_id = detalles[1]["id"]

    assert sol_data["n_bus"] == "BUS-808"
    assert sol_data["estado"] == "REPORTADO"
    assert len(detalles) == 2

    # -------------------------------------------------------------------------
    # PASO 2: Mecánico 1 consulta solicitudes pendientes en Pestaña 1
    # -------------------------------------------------------------------------
    res_pends = await client.get("/api/v1/mantencion/pendientes", headers=auth_headers_mecanico1)
    assert res_pends.status_code == 200
    assert any(s["id"] == sol_id for s in res_pends.json())

    # -------------------------------------------------------------------------
    # PASO 3: Mecánico 1 toma el trabajo como Líder e invita a Mecánico 2
    # -------------------------------------------------------------------------
    res_tomar = await client.post(
        f"/api/v1/mantencion/{sol_id}/tomar",
        json={"colaboradores_ids": [mecanico2_id], "comentario_inicial": "Mecánico 1 y 2 asumen la reparación"},
        headers=auth_headers_mecanico1,
    )
    assert res_tomar.status_code == 200
    sol_en_rep = res_tomar.json()
    assert sol_en_rep["estado"] == "EN_REPARACION"
    assert len(sol_en_rep["mecanicos"]) == 2

    # -------------------------------------------------------------------------
    # PASO 4: Mecánico 1 resuelve la primera falla (det1) y agrega comentario
    # -------------------------------------------------------------------------
    res_check1 = await client.patch(
        f"/api/v1/mantencion/{sol_id}/detalles/{det1_id}/check?resuelto=true",
        headers=auth_headers_mecanico1,
    )
    assert res_check1.status_code == 200
    assert res_check1.json()["detalles"][0]["resuelto"] is True

    res_com1 = await client.post(
        f"/api/v1/mantencion/{sol_id}/comentarios",
        json={"tipo": "AVANCE", "comentario": "Se ajustó manguera del radiador."},
        headers=auth_headers_mecanico1,
    )
    assert res_com1.status_code == 200

    # -------------------------------------------------------------------------
    # PASO 5: Mecánico 1 realiza entrega de turno al finalizar la jornada
    # -------------------------------------------------------------------------
    res_liberar = await client.post(
        f"/api/v1/mantencion/{sol_id}/liberar-turno",
        json={"comentario": "Falta cambiar pastillas de freno en el turno noche."},
        headers=auth_headers_mecanico1,
    )
    assert res_liberar.status_code == 200
    assert res_liberar.json()["estado"] == "PENDIENTE_REASIGNACION"

    # -------------------------------------------------------------------------
    # PASO 6: Mecánico 2 toma el turno nocturno como Líder
    # -------------------------------------------------------------------------
    res_tomar2 = await client.post(
        f"/api/v1/mantencion/{sol_id}/tomar",
        json={"colaboradores_ids": [], "comentario_inicial": "Mecánico 2 retoma orden en turno noche"},
        headers=auth_headers_mecanico2,
    )
    assert res_tomar2.status_code == 200
    assert res_tomar2.json()["estado"] == "EN_REPARACION"

    # -------------------------------------------------------------------------
    # PASO 7: Mecánico 2 resuelve la segunda falla (det2) y finaliza la orden
    # -------------------------------------------------------------------------
    res_check2 = await client.patch(
        f"/api/v1/mantencion/{sol_id}/detalles/{det2_id}/check?resuelto=true",
        headers=auth_headers_mecanico2,
    )
    assert res_check2.status_code == 200

    res_finalizar = await client.post(
        f"/api/v1/mantencion/{sol_id}/finalizar",
        json={"comentario_cierre": "Pastillas instaladas y probadas. Bus liberado."},
        headers=auth_headers_mecanico2,
    )
    assert res_finalizar.status_code == 200
    sol_finalizada = res_finalizar.json()
    assert sol_finalizada["estado"] == "FINALIZADO"
    assert sol_finalizada["mecanico_cierre_id"] == mecanico2_id

    # -------------------------------------------------------------------------
    # PASO 8: Supervisor consulta el Dashboard de Auditoría y verifica trazabilidad
    # -------------------------------------------------------------------------
    res_auditoria = await client.get("/api/v1/supervision/auditoria/buses-taller", headers=auth_headers_supervisor)
    assert res_auditoria.status_code == 200
    lista_auditoria = res_auditoria.json()

    target_auditoria = next((s for s in lista_auditoria if s["id"] == sol_id), None)
    assert target_auditoria is not None
    assert target_auditoria["n_bus"] == "BUS-808"
    assert target_auditoria["estado"] == "FINALIZADO"
    # Verificar que el historial inmutable registre los comentarios y asignaciones
    assert len(target_auditoria["comentarios"]) >= 4
    assert len(target_auditoria["mecanicos"]) >= 3
