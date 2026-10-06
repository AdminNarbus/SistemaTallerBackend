import pytest

from app.core.security import create_access_token, get_password_hash
from app.modules.auth.models.usuario import Usuario
from app.modules.taller.constants import EstadoSolicitud
from app.modules.taller.models.taller_solicitud import TallerSolicitud


@pytest.mark.asyncio
async def test_reportes_del_mismo_bus_se_consolidan_y_preservan_reportante(
    client, db_session, auth_headers_conductor, auth_headers_supervisor, seed_test_data
):
    """Una OT no finalizada absorbe nuevos reportes y conserva su autor por falla."""
    segundo_conductor = Usuario(
        id=6,
        nombre="Ana",
        apellido="Conductora",
        username="conductora2@narbus.cl",
        password_hash=get_password_hash("password123"),
        rol_id=1,
        is_active=True,
    )
    db_session.add(segundo_conductor)
    await db_session.commit()
    segundo_header = {"Authorization": f"Bearer {create_access_token(subject=6)}"}

    primera = await client.post(
        "/api/v1/taller/solicitudes",
        json={
            "n_bus": "OT-CICLO-001",
            "detalles": [{"falla_id": seed_test_data["falla1"].id}],
        },
        headers=auth_headers_conductor,
    )
    assert primera.status_code == 201
    ot_inicial = primera.json()

    # LIBERADO continúa activo: anexar una falla no lo devuelve a PENDIENTE.
    anterior = await db_session.get(TallerSolicitud, ot_inicial["id"])
    anterior.estado = EstadoSolicitud.LIBERADO.value
    await db_session.commit()

    segunda = await client.post(
        "/api/v1/taller/solicitudes",
        json={
            "n_bus": "ot-ciclo-001",
            "detalles": [{"falla_id": seed_test_data["falla2"].id}],
        },
        headers=segundo_header,
    )
    assert segunda.status_code == 201
    ot_consolidada = segunda.json()
    assert ot_consolidada["id"] == ot_inicial["id"]
    assert ot_consolidada["estado"] == EstadoSolicitud.LIBERADO.value
    assert len(ot_consolidada["detalles"]) == 2
    assert {detalle["reportado_por_id"] for detalle in ot_consolidada["detalles"]} == {1, 6}
    assert all(detalle["fecha_reporte"] for detalle in ot_consolidada["detalles"])
    assert all(
        detalle["historial_eventos"][0]["tipo_evento"] == "REPORTADA"
        for detalle in ot_consolidada["detalles"]
    )

    # Sólo FINALIZADO cierra el ciclo; el siguiente reporte abre una OT nueva.
    anterior = await db_session.get(TallerSolicitud, ot_inicial["id"])
    anterior.estado = EstadoSolicitud.FINALIZADO.value
    await db_session.commit()
    tercera = await client.post(
        "/api/v1/taller/solicitudes",
        json={"n_bus": "OT-CICLO-001", "detalles": [{"texto_falla": "Nueva falla"}]},
        headers=auth_headers_conductor,
    )
    assert tercera.status_code == 201
    assert tercera.json()["id"] != ot_inicial["id"]

    # Una OT antigua no puede reabrirse después de que ya existe otra posterior.
    reapertura = await client.patch(
        f"/api/v1/taller/{ot_inicial['id']}/estado",
        json={"estado": "PENDIENTE"},
        headers=auth_headers_supervisor,
    )
    assert reapertura.status_code == 422
    assert "posterior" in reapertura.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_historial_falla_conserva_todos_los_ciclos_de_resolucion(
    client, auth_headers_conductor, auth_headers_mecanico1, seed_test_data
):
    creada = await client.post(
        "/api/v1/taller/solicitudes",
        json={
            "n_bus": "OT-TRAZA-001",
            "detalles": [{"falla_id": seed_test_data["falla1"].id}],
        },
        headers=auth_headers_conductor,
    )
    assert creada.status_code == 201
    solicitud = creada.json()
    detalle_id = solicitud["detalles"][0]["id"]

    for estado in ("RESUELTA", "PENDIENTE", "RESUELTA"):
        cambio = await client.patch(
            f"/api/v1/taller/{solicitud['id']}/detalles/{detalle_id}/check",
            json={"estado": estado, "comentario": f"Cambio a {estado}"},
            headers=auth_headers_mecanico1,
        )
        assert cambio.status_code == 200

    consulta = await client.get(
        f"/api/v1/taller/{solicitud['id']}",
        headers=auth_headers_mecanico1,
    )
    assert consulta.status_code == 200
    historial = consulta.json()["detalles"][0]["historial_eventos"]
    assert [evento["tipo_evento"] for evento in historial] == [
        "REPORTADA", "RESUELTA", "REABIERTA", "RESUELTA",
    ]
    resoluciones = [evento for evento in historial if evento["tipo_evento"] == "RESUELTA"]
    assert all(evento["mecanicos_resolvieron"] for evento in resoluciones)
