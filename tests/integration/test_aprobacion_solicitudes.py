from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.modules.buses.models.bus import Bus
from app.modules.taller.constants import EstadoSolicitud
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario


@pytest.fixture
async def solicitud_nueva(client, db_session, auth_headers_conductor):
    bus = Bus(n_bus="APR-101", patente="APR-101", is_active=True, en_taller=False)
    db_session.add(bus)
    await db_session.commit()
    response = await client.post("/api/v1/taller/solicitudes", headers=auth_headers_conductor, json={
        "bus_id": bus.id, "detalles": [{"nombre": "Freno largo"}],
    })
    assert response.status_code == 201, response.text
    resultado = response.json()
    assert resultado["es_ot"] is False
    assert resultado["estado"] is None
    return resultado


async def test_solicitud_sin_aprobar_oculta_estado_en_listas_y_detalle(
    client, solicitud_nueva, auth_headers_mecanico1, auth_headers_supervisor,
):
    rutas = [f"/api/v1/taller/{solicitud_nueva['id']}", "/api/v1/taller/pendientes", "/api/v1/taller/buses"]
    for ruta in rutas:
        res = await client.get(ruta, headers=auth_headers_mecanico1)
        assert res.status_code == 200, res.text
        data = res.json()
        registro = data[0]["ot"] if ruta.endswith("/buses") else (data[0] if isinstance(data, list) else data)
        assert registro["es_ot"] is False
        assert registro["estado"] is None
    auditoria = await client.get("/api/v1/supervision/auditoria/buses-taller", headers=auth_headers_supervisor)
    assert auditoria.status_code == 200, auditoria.text
    assert auditoria.json()[0]["es_ot"] is False
    assert auditoria.json()[0]["estado"] is None


async def test_supervision_aprueba_una_sola_vez_y_no_ingresa_al_bus(
    client, db_session, solicitud_nueva, auth_headers_supervisor,
):
    ruta = f"/api/v1/taller/{solicitud_nueva['id']}/aprobar"
    for _ in range(2):
        response = await client.post(ruta, json={"comentario": "Aprobada para turno de tarde"}, headers=auth_headers_supervisor)
        assert response.status_code == 200, response.text
        aprobada = response.json()
        assert aprobada["es_ot"] is True
        assert aprobada["estado"] == "PENDIENTE"
        assert aprobada["id"] == solicitud_nueva["id"]
        assert aprobada["fecha_creacion"] == solicitud_nueva["fecha_creacion"]
        assert len(aprobada["detalles"]) == 1
        assert aprobada["estadias"] == []
    assert await db_session.scalar(select(Bus.en_taller).where(Bus.id == solicitud_nueva["bus_id"])) is False
    aprobaciones = await db_session.scalar(select(func.count()).select_from(TallerSolicitudComentario).where(
        TallerSolicitudComentario.solicitud_id == solicitud_nueva["id"],
        TallerSolicitudComentario.comentario.like("Solicitud aprobada como OT.%"),
    ))
    assert aprobaciones == 1


@pytest.mark.parametrize("operacion", ["tomar", "autoasignar", "asignar"])
async def test_inicio_o_asignacion_aprueba_en_la_misma_operacion(
    client, db_session, solicitud_nueva, auth_headers_mecanico1, auth_headers_supervisor, operacion,
):
    payload = {} if operacion == "tomar" else {"detalles_ids": [solicitud_nueva["detalles"][0]["id"]]}
    headers = auth_headers_mecanico1
    if operacion == "asignar":
        payload["mecanicos_ids"] = [2]
        headers = auth_headers_supervisor
    response = await client.post(f"/api/v1/taller/{solicitud_nueva['id']}/{operacion}", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["es_ot"] is True
    assert data["estado"] == "EN_REPARACION"
    assert len(data["estadias"]) == 1
    assert await db_session.scalar(select(TallerSolicitud.es_ot).where(TallerSolicitud.id == data["id"])) is True


async def test_falla_asignada_por_supervision_aprueba_solicitud(
    client, solicitud_nueva, auth_headers_supervisor,
):
    response = await client.post(f"/api/v1/taller/{solicitud_nueva['id']}/detalles", headers=auth_headers_supervisor,
                                 json={"nombre": "Fuga adicional", "mecanico_asignado_id": 2})
    assert response.status_code == 201, response.text
    assert response.json()["es_ot"] is True
    assert response.json()["estado"] == "EN_REPARACION"


async def test_mecanico_no_puede_aprobar_sin_asignarse(client, solicitud_nueva, auth_headers_mecanico1):
    response = await client.post(f"/api/v1/taller/{solicitud_nueva['id']}/aprobar", json={}, headers=auth_headers_mecanico1)
    assert response.status_code == 403


async def test_solicitud_no_se_cierra_ni_cambia_estado_sin_aprobar(
    client, solicitud_nueva, auth_headers_supervisor, auth_headers_mecanico1,
):
    sid = solicitud_nueva["id"]
    cambio = await client.patch(f"/api/v1/taller/{sid}/estado", json={"estado": "LIBERADO"}, headers=auth_headers_supervisor)
    assert cambio.status_code == 422
    cierre = await client.post(f"/api/v1/taller/{sid}/finalizar", json={}, headers=auth_headers_mecanico1)
    assert cierre.status_code == 422


async def test_ot_no_vuelve_a_solicitud_al_liberarse_o_volver_a_pendiente(
    client, solicitud_nueva, auth_headers_supervisor,
):
    sid = solicitud_nueva["id"]
    aprobada = await client.post(f"/api/v1/taller/{sid}/aprobar", json={}, headers=auth_headers_supervisor)
    assert aprobada.status_code == 200
    for estado in ("LIBERADO", "PENDIENTE"):
        cambio = await client.patch(f"/api/v1/taller/{sid}/estado", json={"estado": estado}, headers=auth_headers_supervisor)
        assert cambio.status_code == 200, cambio.text
        assert cambio.json()["es_ot"] is True
        assert cambio.json()["estado"] == estado


def test_estados_canonicos_siguen_siendo_cuatro():
    assert {e.value for e in EstadoSolicitud} == {"PENDIENTE", "EN_REPARACION", "LIBERADO", "FINALIZADO"}
