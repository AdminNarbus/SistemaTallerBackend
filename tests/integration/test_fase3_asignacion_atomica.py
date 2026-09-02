import pytest
from app.modules.buses.models.bus import Bus


@pytest.mark.asyncio
async def test_flujo_fase3_asignacion_atomica_y_coresponsabilidad(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
    auth_headers_mecanico1,
    auth_headers_mecanico2,
    auth_headers_supervisor,
):
    """
    Verifica de punta a punta:
    1. Creación de solicitud con 2 fallas específicas.
    2. Mecánico 1 se autoasigna Falla 1 (estado -> EN_REPARACION).
    3. Mecánico 2 se autoasigna también Falla 1 (Co-responsabilidad: ambos activos en Falla 1).
    4. Mecánico 2 se autoasigna Falla 2 (solo Mecánico 2 en Falla 2).
    5. Supervisora asigna Falla 2 a Mecánico 1 vía /supervision/solicitudes/{id}/asignar (co-responsables en Falla 2).
    6. Mecánico 1 termina su avance en Falla 1 -> Falla 1 sigue activa para Mecánico 2.
    7. Mecánicos terminan todos sus avances -> Solicitud retorna a PENDIENTE.
    8. Control RBAC: Conductor no puede autoasignarse y mecánico no puede usar endpoint de supervisión.
    """
    # 0. Crear un Bus
    bus = Bus(id=10, n_bus="301", patente="BC3001", marca="Scania", modelo="K400", is_active=True, en_taller=False)
    db_session.add(bus)
    await db_session.commit()

    # 1. Chofer crea solicitud con 2 fallas
    payload_solicitud = {
        "n_bus": "301",
        "descripcion_general": "Fallas detectadas en ruta matinal",
        "detalles": [
            {"falla_id": 1, "descripcion_personalizada": "Pérdida severa de líquido refrigerante"},
            {"falla_id": 2, "descripcion_personalizada": "Pastillas delanteras desgastadas al 90%"},
        ],
    }
    res_crear = await client.post("/api/v1/mantencion/solicitudes", json=payload_solicitud, headers=auth_headers_conductor)
    assert res_crear.status_code == 201
    data_sol = res_crear.json()
    sol_id = data_sol["id"]
    assert data_sol["estado"] == "REPORTADO"
    assert len(data_sol["detalles"]) == 2
    det1_id = data_sol["detalles"][0]["id"]
    det2_id = data_sol["detalles"][1]["id"]

    # 2. Mecánico 1 se autoasigna Falla 1
    res_auto1 = await client.post(
        f"/api/v1/mantencion/{sol_id}/autoasignar",
        json={"detalles_ids": [det1_id], "comentario": "Revisando manguera de radiador"},
        headers=auth_headers_mecanico1,
    )
    assert res_auto1.status_code == 200
    data_auto1 = res_auto1.json()
    assert data_auto1["estado"] == "EN_REPARACION"
    det1 = next(d for d in data_auto1["detalles"] if d["id"] == det1_id)
    assert len(det1["mecanicos_asignados"]) == 1
    assert det1["mecanicos_asignados"][0]["id"] == 2
    assert det1["mecanicos_asignados"][0]["origen"] == "AUTOASIGNACION"

    # 3. Mecánico 2 se autoasigna también Falla 1 (CO-RESPONSABILIDAD)
    res_auto2_falla1 = await client.post(
        f"/api/v1/mantencion/{sol_id}/autoasignar",
        json={"detalles_ids": [det1_id], "comentario": "Apoyando en purga de sistema"},
        headers=auth_headers_mecanico2,
    )
    assert res_auto2_falla1.status_code == 200
    data_coresp = res_auto2_falla1.json()
    det1_coresp = next(d for d in data_coresp["detalles"] if d["id"] == det1_id)
    # Deben estar AMBOS mecánicos activos en la Falla 1
    mec_ids_falla1 = [m["id"] for m in det1_coresp["mecanicos_asignados"]]
    assert 2 in mec_ids_falla1
    assert 3 in mec_ids_falla1

    # 4. Mecánico 2 se autoasigna Falla 2
    res_auto2_falla2 = await client.post(
        f"/api/v1/mantencion/{sol_id}/autoasignar",
        json={"detalles_ids": [det2_id], "comentario": "Desmontando calipers"},
        headers=auth_headers_mecanico2,
    )
    assert res_auto2_falla2.status_code == 200
    det2 = next(d for d in res_auto2_falla2.json()["detalles"] if d["id"] == det2_id)
    assert len(det2["mecanicos_asignados"]) == 1
    assert det2["mecanicos_asignados"][0]["id"] == 3

    # 5. Supervisora asigna Falla 2 también al Mecánico 1 vía /supervision/solicitudes/{id}/asignar
    res_sup_asig = await client.post(
        f"/api/v1/supervision/solicitudes/{sol_id}/asignar",
        json={"mecanico_id": 2, "detalles_ids": [det2_id], "comentario": "Prioridad alta solicitada por gerencia"},
        headers=auth_headers_supervisor,
    )
    assert res_sup_asig.status_code == 200
    det2_sup = next(d for d in res_sup_asig.json()["detalles"] if d["id"] == det2_id)
    mec_ids_falla2 = [m["id"] for m in det2_sup["mecanicos_asignados"]]
    assert 2 in mec_ids_falla2
    assert 3 in mec_ids_falla2
    asig_mec1_falla2 = next(m for m in det2_sup["mecanicos_asignados"] if m["id"] == 2)
    assert asig_mec1_falla2["origen"] == "SUPERVISOR"

    # 6. Mecánico 1 termina su avance en Falla 1
    res_fin_mec1_f1 = await client.post(
        f"/api/v1/mantencion/{sol_id}/terminar-avance",
        json={"detalles_ids": [det1_id], "comentario": "Reemplazo de abrazadera completado"},
        headers=auth_headers_mecanico1,
    )
    assert res_fin_mec1_f1.status_code == 200
    data_fin_m1 = res_fin_mec1_f1.json()
    det1_post_fin = next(d for d in data_fin_m1["detalles"] if d["id"] == det1_id)
    # Mecánico 1 ya no está activo en Falla 1, pero Mecánico 2 SIGUE ACTIVO
    mec_ids_f1_post = [m["id"] for m in det1_post_fin["mecanicos_asignados"]]
    assert 2 not in mec_ids_f1_post
    assert 3 in mec_ids_f1_post
    # La orden sigue EN_REPARACION
    assert data_fin_m1["estado"] == "EN_REPARACION"

    # 7. Mecánico 1 termina su avance en Falla 2 y Mecánico 2 termina avance en todas sus fallas
    await client.post(
        f"/api/v1/mantencion/{sol_id}/terminar-avance",
        json={"detalles_ids": [det2_id]},
        headers=auth_headers_mecanico1,
    )
    res_fin_total = await client.post(
        f"/api/v1/mantencion/{sol_id}/terminar-avance",
        json={"comentario": "Fin de turno noche sin cerrar todas las fallas"},
        headers=auth_headers_mecanico2,
    )
    assert res_fin_total.status_code == 200
    data_final = res_fin_total.json()
    # Como no quedan mecánicos asignados activamente, la solicitud pasa a PENDIENTE
    assert data_final["estado"] == "PENDIENTE"

    # 8. Verificación de permisos (RBAC)
    # Conductor intenta autoasignarse -> 403
    res_cond_auto = await client.post(
        f"/api/v1/mantencion/{sol_id}/autoasignar",
        json={"detalles_ids": [det1_id]},
        headers=auth_headers_conductor,
    )
    assert res_cond_auto.status_code == 403

    # Mecánico intenta asignar por endpoint de supervisión -> 403
    res_mec_sup = await client.post(
        f"/api/v1/supervision/solicitudes/{sol_id}/asignar",
        json={"mecanico_id": 3, "detalles_ids": [det1_id]},
        headers=auth_headers_mecanico1,
    )
    assert res_mec_sup.status_code == 403
