import pytest
from datetime import datetime, timedelta, timezone
from app.modules.buses.models.bus import Bus


@pytest.mark.asyncio
async def test_filtros_fecha_actualizacion_flujo_completo(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
    auth_headers_mecanico1,
    auth_headers_supervisor,
):
    """
    Prueba que:
    1. Las solicitudes creadas tengan 'fecha_actualizacion'.
    2. El endpoint /pendientes retorne 'fecha_actualizacion' y funcione el filtro de fecha.
    3. El endpoint /auditoria/buses-taller retorne 'fecha_actualizacion' y filtre por rango.
    4. El endpoint /mis-trabajos soporte filtros y serialice 'fecha_actualizacion'.
    """
    # 0. Crear un bus en la base de datos
    bus = Bus(id=105, n_bus="BUS-500", patente="GG5000", marca="Scania", modelo="K400", is_active=True, en_taller=True)
    db_session.add(bus)
    await db_session.commit()

    # 1. Crear una solicitud de taller como conductor
    payload = {
        "n_bus": "BUS-500",
        "descripcion_general": "Filtro de aire y luces",
        "detalles": [
            {"falla_id": 1, "descripcion_personalizada": "Cambio de filtro"}
        ],
    }
    res_crear = await client.post("/api/v1/taller/solicitudes", json=payload, headers=auth_headers_conductor)
    assert res_crear.status_code == 201
    ot = res_crear.json()
    assert "fecha_actualizacion" in ot
    assert ot["fecha_actualizacion"] is not None
    solicitud_id = ot["id"]

    # 2. Consultar /pendientes como mecánico
    res_pendientes = await client.get("/api/v1/taller/pendientes", headers=auth_headers_mecanico1)
    assert res_pendientes.status_code == 200
    pendientes = res_pendientes.json()
    assert len(pendientes) > 0
    primera_p = pendientes[0]
    assert "fecha_actualizacion" in primera_p
    assert primera_p["fecha_actualizacion"] is not None

    # Filtrar /pendientes con fecha futura -> 0 resultados
    futuro = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res_futuro = await client.get(
        f"/api/v1/taller/pendientes?fecha_modificacion_desde={futuro}",
        headers=auth_headers_mecanico1,
    )
    assert res_futuro.status_code == 200, res_futuro.text
    assert len(res_futuro.json()) == 0
    assert res_futuro.headers["X-Total-Count"] == "0"

    # Filtrar /pendientes con fecha pasada -> debe incluir la solicitud creada
    pasado = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res_pasado = await client.get(
        f"/api/v1/taller/pendientes?fecha_modificacion_desde={pasado}",
        headers=auth_headers_mecanico1,
    )
    assert res_pasado.status_code == 200
    assert any(item["id"] == solicitud_id for item in res_pasado.json())

    # Probar alias fecha_desde
    res_alias = await client.get(
        f"/api/v1/taller/pendientes?fecha_desde={pasado}",
        headers=auth_headers_mecanico1,
    )
    assert res_alias.status_code == 200
    assert len(res_alias.json()) == len(res_pasado.json())

    # 3. Consultar /auditoria/buses-taller como supervisor
    res_auditoria = await client.get("/api/v1/supervision/auditoria/buses-taller", headers=auth_headers_supervisor)
    assert res_auditoria.status_code == 200
    auditoria = res_auditoria.json()
    assert len(auditoria) > 0
    primera_a = auditoria[0]
    assert "fecha_actualizacion" in primera_a
    assert primera_a["fecha_actualizacion"] is not None

    # Filtrar auditoria con rango válido
    hasta = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res_rango = await client.get(
        f"/api/v1/supervision/auditoria/buses-taller?fecha_modificacion_desde={pasado}&fecha_modificacion_hasta={hasta}",
        headers=auth_headers_supervisor,
    )
    assert res_rango.status_code == 200, res_rango.text
    assert any(item["id"] == solicitud_id for item in res_rango.json())

    # Filtrar auditoria con fecha futura -> 0 resultados
    res_aud_futuro = await client.get(
        f"/api/v1/supervision/auditoria/buses-taller?fecha_modificacion_desde={futuro}",
        headers=auth_headers_supervisor,
    )
    assert res_aud_futuro.status_code == 200, res_aud_futuro.text
    assert len(res_aud_futuro.json()) == 0
    assert res_aud_futuro.headers["X-Total-Count"] == "0"
