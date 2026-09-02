import pytest
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.pauta_taller import PautaTallerItem


@pytest.mark.asyncio
async def test_flujo_fase5_supervision_metricas_y_alertas(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
    auth_headers_mecanico1,
    auth_headers_supervisor,
):
    """
    Verifica de punta a punta Fase 5:
    1. Creación de bus físicamente en taller y solicitud con fallas.
    2. Reporte de falta de repuestos en una falla.
    3. Registro de pauta preventiva con ítem en DEFECTO.
    4. Consulta de resumen y KPIs con buses_fisicamente_en_taller y fallas_bloqueadas_por_repuesto.
    5. Consulta de endpoint de alertas activas (REPUESTO_FALTANTE, DEFECTO_PAUTA).
    6. Verificación de control de acceso RBAC (403 para mecánicos/conductores).
    """
    # 0. Sembrar ítem de pauta preventiva
    pauta_item = PautaTallerItem(id=1, categoria="Frenos", item="Espesor de balatas delanteras", orden=1, is_active=True)
    db_session.add(pauta_item)

    # Bus en taller
    bus = Bus(id=50, n_bus="305", patente="EF3005", marca="Mercedes-Benz", modelo="O500", is_active=True, en_taller=True)
    db_session.add(bus)
    await db_session.commit()

    # 1. Conductor crea reporte de taller
    payload_sol = {
        "n_bus": "305",
        "descripcion_general": "Fuga de aire y freno largo",
        "detalles": [
            {"falla_id": 1, "descripcion_personalizada": "Compresor de aire no carga presión"},
            {"falla_id": 2, "descripcion_personalizada": "Válvula pedalera con fuga continua"},
        ],
    }
    res_crear = await client.post("/api/v1/mantencion/solicitudes", json=payload_sol, headers=auth_headers_conductor)
    assert res_crear.status_code == 201
    data_sol = res_crear.json()
    sol_id = data_sol["id"]
    det1_id = data_sol["detalles"][0]["id"]

    # 2. Mecánico reporta falta de repuesto para Falla 1
    res_repuesto = await client.patch(
        f"/api/v1/mantencion/{sol_id}/detalles/{det1_id}/repuesto",
        json={"falta_repuesto": True, "comentario": "Falta kit de reparación para compresor Knorr"},
        headers=auth_headers_mecanico1,
    )
    assert res_repuesto.status_code == 200

    # 3. Mecánico registra pauta con defecto
    res_pauta = await client.post(
        f"/api/v1/mantencion/{sol_id}/pauta",
        json={"respuestas": [{"item_id": 1, "estado": "DEFECTO", "observacion": "Balatas con desgaste crítico bajo límite"}]},
        headers=auth_headers_mecanico1,
    )
    assert res_pauta.status_code == 200

    # 4. Supervisora consulta resumen general del taller
    res_resumen = await client.get("/api/v1/supervision/resumen-taller", headers=auth_headers_supervisor)
    assert res_resumen.status_code == 200
    data_resumen = res_resumen.json()

    metricas = data_resumen["metricas_estado"]
    assert metricas["buses_fisicamente_en_taller"] >= 1
    assert metricas["fallas_bloqueadas_por_repuesto"] >= 1
    assert "305" in data_resumen["buses_activos_taller"]

    # 5. Supervisora consulta Centro de Alertas
    res_alertas = await client.get("/api/v1/supervision/alertas", headers=auth_headers_supervisor)
    assert res_alertas.status_code == 200
    alertas = res_alertas.json()
    assert len(alertas) >= 2

    # Verificar alerta de repuesto
    alerta_rep = next((a for a in alertas if a["tipo"] == "REPUESTO_FALTANTE" and a["solicitud_id"] == sol_id), None)
    assert alerta_rep is not None
    assert alerta_rep["severidad"] == "ALTA"
    assert "Falta kit de reparación" in alerta_rep["mensaje"]

    # Verificar alerta de defecto en pauta
    alerta_def = next((a for a in alertas if a["tipo"] == "DEFECTO_PAUTA" and a["solicitud_id"] == sol_id), None)
    assert alerta_def is not None
    assert alerta_def["severidad"] == "MEDIA"
    assert "Espesor de balatas delanteras" in alerta_def["mensaje"]

    # 6. Restricción RBAC: mecánicos y conductores no tienen permiso a /alertas
    res_unauth_mec = await client.get("/api/v1/supervision/alertas", headers=auth_headers_mecanico1)
    assert res_unauth_mec.status_code == 403

    res_unauth_con = await client.get("/api/v1/supervision/alertas", headers=auth_headers_conductor)
    assert res_unauth_con.status_code == 403
