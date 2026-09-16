import pytest
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.pauta_taller import PautaTallerItem


@pytest.mark.asyncio
async def test_flujo_fase4_pauta_repuestos_y_liberacion(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
    auth_headers_mecanico1,
):
    """
    Verifica de punta a punta:
    1. Siembra de ítems de pauta preventiva y creación de solicitud con bus en taller.
    2. Reporte de falta de repuesto en una falla.
    3. Consulta de ítems y estado inicial de pauta (0/11).
    4. Carga parcial de pauta (6/11).
    5. Intento de liberación con pauta incompleta sin justificación -> 422.
    6. Liberación con justificación de pauta incompleta, pero con fallas abiertas sin motivo_cierre_parcial -> 422.
    7. Cierre parcial exitoso con motivo_incompleto_checklist y motivo_cierre_parcial -> 200 y bus pasa a en_taller=False.
    """
    # 0. Sembrar 11 ítems de pauta preventiva si no existen
    items_exist = [
        PautaTallerItem(id=i, categoria="General", item=f"Revisión preventiva item {i}", orden=i, is_active=True)
        for i in range(1, 12)
    ]
    db_session.add_all(items_exist)

    # Crear bus y marcarlo en taller
    bus = Bus(id=20, n_bus="302", patente="CD3002", marca="Scania", modelo="K400", is_active=True, en_taller=True)
    db_session.add(bus)
    await db_session.commit()

    # 1. Crear solicitud con 2 fallas
    payload_solicitud = {
        "n_bus": "302",
        "descripcion_general": "Revisión programada y ruidos en tren delantero",
        "detalles": [
            {"falla_id": 1, "descripcion_personalizada": "Rueda delantera con juego axial"},
            {"falla_id": 2, "descripcion_personalizada": "Bomba de agua con fuga intermitente"},
        ],
    }
    res_crear = await client.post("/api/v1/mantencion/solicitudes", json=payload_solicitud, headers=auth_headers_conductor)
    assert res_crear.status_code == 201
    data_sol = res_crear.json()
    sol_id = data_sol["id"]
    det1_id = data_sol["detalles"][0]["id"]
    det2_id = data_sol["detalles"][1]["id"]

    # 2. Mecánico reporta falta de repuesto en Falla 2 — responde DetalleUpdateDTO (Nivel 3)
    res_repuesto = await client.patch(
        f"/api/v1/mantencion/{sol_id}/detalles/{det2_id}/repuesto",
        json={"falta_repuesto": True, "comentario": "Se requiere kit de empaquetaduras y rodamiento"},
        headers=auth_headers_mecanico1,
    )
    assert res_repuesto.status_code == 200
    data_rep = res_repuesto.json()
    assert data_rep["detalle_id"] == det2_id
    assert data_rep["falta_repuesto"] is True
    assert data_rep["comentario_repuesto"] == "Se requiere kit de empaquetaduras y rodamiento"

    # Mecánico resuelve Falla 1 — responde DetalleUpdateDTO (Nivel 3)
    res_check1 = await client.patch(
        f"/api/v1/mantencion/{sol_id}/detalles/{det1_id}/check?resuelto=true",
        headers=auth_headers_mecanico1,
    )
    assert res_check1.status_code == 200
    assert res_check1.json()["resuelto"] is True

    # 3. Consultar ítems de la pauta preventiva
    res_pauta_items = await client.get("/api/v1/mantencion/pauta/items", headers=auth_headers_mecanico1)
    assert res_pauta_items.status_code == 200
    pauta_items = res_pauta_items.json()
    assert len(pauta_items) >= 11

    # Consultar estado de pauta para esta solicitud
    res_pauta_sol = await client.get(f"/api/v1/mantencion/{sol_id}/pauta", headers=auth_headers_mecanico1)
    assert res_pauta_sol.status_code == 200
    data_pauta = res_pauta_sol.json()
    assert data_pauta["respondidos"] == 0
    assert data_pauta["completado"] is False

    # 4. Registrar 6 respuestas de pauta
    respuestas_6 = [{"item_id": i, "estado": "OK", "observacion": "Conforme"} for i in range(1, 7)]
    res_guardar_pauta = await client.post(
        f"/api/v1/mantencion/{sol_id}/pauta",
        json={"respuestas": respuestas_6},
        headers=auth_headers_mecanico1,
    )
    assert res_guardar_pauta.status_code == 200
    data_pauta_post = res_guardar_pauta.json()
    assert data_pauta_post["respondidos"] == 6
    assert data_pauta_post["pendientes"] == 5
    assert data_pauta_post["completado"] is False

    # 5. Intentar liberar con pauta incompleta sin motivo_incompleto_checklist -> 422 (BusinessRuleException)
    res_lib_invalida_pauta = await client.post(
        f"/api/v1/mantencion/{sol_id}/liberar",
        json={"comentario_cierre": "Listo para salir"},
        headers=auth_headers_mecanico1,
    )
    assert res_lib_invalida_pauta.status_code == 422
    assert "pauta preventiva está incompleta" in res_lib_invalida_pauta.json()["error"]["message"]

    # 6. Intentar liberar justificando pauta, pero sin motivo_cierre_parcial para la falla 2 pendiente -> 422
    res_lib_invalida_fallas = await client.post(
        f"/api/v1/mantencion/{sol_id}/liberar",
        json={
            "motivo_incompleto_checklist": "No se revisaron items 7 a 11 por urgencia de horario",
            "comentario_cierre": "Liberando bus",
        },
        headers=auth_headers_mecanico1,
    )
    assert res_lib_invalida_fallas.status_code == 422
    assert "falla(s) no resueltas o con falta de repuestos" in res_lib_invalida_fallas.json()["error"]["message"]

    # 7. Liberar correctamente con justificaciones completas
    res_lib_ok = await client.post(
        f"/api/v1/mantencion/{sol_id}/liberar",
        json={
            "motivo_incompleto_checklist": "No se revisaron items 7 a 11 por urgencia de horario",
            "motivo_cierre_parcial": "Falla 2 postergada por repuesto de bomba en tránsito desde Santiago",
            "comentario_cierre": "Bus liberado con cierre parcial autorizado",
            "liberar_bus_taller": True,
        },
        headers=auth_headers_mecanico1,
    )
    assert res_lib_ok.status_code == 200
    data_lib = res_lib_ok.json()
    assert data_lib["estado"] == "LIBERADO"
    assert data_lib["fecha_cierre"] is None
    assert data_lib["motivo_incompleto_checklist"] == "No se revisaron items 7 a 11 por urgencia de horario"
    assert data_lib["motivo_cierre_parcial"] == "Falla 2 postergada por repuesto de bomba en tránsito desde Santiago"

    # Verificar que el bus ya NO está en taller
    res_bus = await client.get("/api/v1/buses/20")
    assert res_bus.status_code == 200
    assert res_bus.json()["en_taller"] is False
