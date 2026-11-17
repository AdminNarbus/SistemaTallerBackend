from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.modules.buses.models.bus import Bus
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.services.revision_falla_service import puede_aprobar_reporte


@pytest.fixture
async def ot_aceptada(client, db_session, auth_headers_conductor, auth_headers_supervisor):
    bus = Bus(n_bus="REV-101", patente="REV-101", is_active=True, en_taller=False)
    db_session.add(bus)
    await db_session.commit()
    res = await client.post("/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"bus_id": bus.id, "detalles": [{"nombre": "Falla original"}]})
    assert res.status_code == 201, res.text
    sid = res.json()["id"]
    res = await client.post(f"/api/v1/taller/{sid}/aprobar", headers=auth_headers_supervisor, json={})
    assert res.status_code == 200, res.text
    assert res.json()["detalles"][0]["estado_revision"] == "APROBADA"
    return res.json()


@pytest.mark.parametrize("autoasignar", [False, True])
async def test_revision_mecanico_sin_asignacion_depende_de_autoasignacion(
    client, ot_aceptada, auth_headers_mecanico1, autoasignar,
):
    sid = ot_aceptada["id"]
    res = await client.post(f"/api/v1/taller/{sid}/detalles", headers=auth_headers_mecanico1,
        json={"nombre": "Falla sin visto bueno", "autoasignar": autoasignar})
    assert res.status_code == 201, res.text
    nueva = res.json()["detalles"][-1]
    assert nueva["estado_revision"] == ("APROBADA" if autoasignar else "PENDIENTE")
    assert nueva["revisado_por_id"] == (2 if autoasignar else None)
    assert bool(nueva["fecha_revision"]) is autoasignar
    assert bool(nueva["mecanicos_asignados"]) is autoasignar
    res = await client.post(f"/api/v1/taller/{sid}/autoasignar", headers=auth_headers_mecanico1,
        json={"detalles_ids": [nueva["id"]]})
    assert res.status_code == 200, res.text
    assert res.json()["detalles"][-1]["estado_revision"] == "APROBADA"


async def test_reporte_conductor_en_ot_existente_y_aprobacion_individual(
    client, db_session, ot_aceptada, auth_headers_conductor, auth_headers_supervisor, auth_headers_mecanico1,
):
    sid = ot_aceptada["id"]
    res = await client.post("/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"bus_id": ot_aceptada["bus_id"], "detalles": [{"nombre": "Nueva del conductor"}]})
    assert res.status_code == 201, res.text
    assert res.json()["id"] == sid
    nueva = res.json()["detalles"][-1]
    assert nueva["estado_revision"] == "PENDIENTE"
    # Reaprobar la cabecera no aprueba nuevas fallas de forma masiva.
    res = await client.post(f"/api/v1/taller/{sid}/aprobar", headers=auth_headers_supervisor, json={})
    assert res.json()["detalles"][-1]["estado_revision"] == "PENDIENTE"
    url = f"/api/v1/supervision/solicitudes/{sid}/detalles/{nueva['id']}/aprobar"
    res = await client.patch(url, headers=auth_headers_mecanico1)
    assert res.status_code == 403
    for _ in range(2):
        res = await client.patch(url, headers=auth_headers_supervisor)
        assert res.status_code == 200, res.text
        detalle = res.json()["detalles"][-1]
        assert detalle["estado_revision"] == "APROBADA"
        assert detalle["revisado_por_id"] == 4
        assert detalle["fecha_revision"]
    count = await db_session.scalar(select(func.count()).select_from(TallerSolicitudComentario).where(
        TallerSolicitudComentario.comentario == f"Falla #{nueva['id']} aprobada por supervisión."))
    assert count == 1


@pytest.mark.parametrize("via", ["detalle", "reporte"])
async def test_mecanico_con_falla_asignada_conserva_aprobacion_automatica(
    client, db_session, ot_aceptada, auth_headers_supervisor, auth_headers_mecanico1, via,
):
    sid = ot_aceptada["id"]
    res = await client.post(f"/api/v1/taller/{sid}/asignar", headers=auth_headers_supervisor,
        json={"detalles_ids": [ot_aceptada["detalles"][0]["id"]], "mecanicos_ids": [2]})
    assert res.status_code == 200, res.text
    url = f"/api/v1/taller/{sid}/detalles" if via == "detalle" else "/api/v1/taller/solicitudes"
    payload = {"nombre": "Hallazgo", "autoasignar": False} if via == "detalle" else {
        "bus_id": ot_aceptada["bus_id"], "detalles": [{"nombre": "Hallazgo"}]}
    if via == "reporte":
        from app.modules.taller.services.solicitud_service import solicitud_service
        from app.modules.taller.dtos import SolicitudCreateDTO
        resultado = await solicitud_service.create_solicitud(db_session, SolicitudCreateDTO(**payload),
            creador_id=2, creador_nombre="Pedro Mecanico", creador_rol="MECANICO")
        nueva = resultado.model_dump()["detalles"][-1]
    else:
        res = await client.post(url, headers=auth_headers_mecanico1, json=payload)
        assert res.status_code == 201, res.text
        nueva = res.json()["detalles"][-1]
    assert nueva["estado_revision"] == "APROBADA"
    assert nueva["revisado_por_id"] == 2
    assert nueva["fecha_revision"]


@pytest.mark.parametrize("rol,asignado,esperado", [
    ("CONDUCTOR", True, False), ("MECANICO", False, False),
    ("MECANICO", True, True), ("SUPERVISOR", False, True), ("ADMIN", False, True),
])
async def test_regla_revision_aislada(rol, asignado, esperado):
    repo = SimpleNamespace(get_asignaciones_activas=AsyncMock(return_value=[
        SimpleNamespace(mecanico_id=2 if asignado else 3)]))
    assert await puede_aprobar_reporte(None, (repo, 1, 2, rol)) is esperado


async def test_autoasignar_aprueba_solo_fallas_seleccionadas(
    client, ot_aceptada, auth_headers_conductor, auth_headers_mecanico1,
):
    sid = ot_aceptada["id"]
    res = await client.post("/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"bus_id": ot_aceptada["bus_id"], "detalles": [{"nombre": "A"}, {"nombre": "B"}]})
    assert res.status_code == 201, res.text
    seleccionada, otra = res.json()["detalles"][-2:]
    res = await client.post(f"/api/v1/taller/{sid}/autoasignar", headers=auth_headers_mecanico1,
        json={"detalles_ids": [seleccionada["id"]]})
    assert res.status_code == 200, res.text
    detalles = {d["id"]: d for d in res.json()["detalles"]}
    assert detalles[seleccionada["id"]]["estado_revision"] == "APROBADA"
    assert detalles[seleccionada["id"]]["revisado_por_id"] == 2
    assert detalles[otra["id"]]["estado_revision"] == "PENDIENTE"


async def test_pendiente_no_admite_check_antes_de_revision(
    client, ot_aceptada, auth_headers_conductor, db_session,
):
    from app.core.exceptions import BusinessRuleException
    from app.modules.taller.services.averias_service import averias_service
    sid = ot_aceptada["id"]
    res = await client.post("/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"bus_id": ot_aceptada["bus_id"], "detalles": [{"nombre": "Sin revisión"}]})
    nueva = res.json()["detalles"][-1]
    with pytest.raises(BusinessRuleException, match="visto bueno"):
        await averias_service.check_detalle(db_session, sid, nueva["id"], 2, resuelto=True)


@pytest.mark.parametrize("operacion", ["tomar", "autoasignar", "asignar"])
async def test_aprobacion_inicial_respeta_alcance_y_no_aprueba_reportes_posteriores(
    client, auth_headers_conductor, auth_headers_mecanico1, auth_headers_supervisor, operacion,
):
    res = await client.post("/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"n_bus": "INICIAL-REV", "detalles": [{"nombre": "Inicial A"}, {"nombre": "Inicial B"}]})
    assert res.status_code == 201, res.text
    solicitud = res.json()
    sid = solicitud["id"]
    payload = {} if operacion == "tomar" else {"detalles_ids": [solicitud["detalles"][0]["id"]]}
    headers = auth_headers_mecanico1
    if operacion == "asignar":
        payload["mecanicos_ids"] = [2]
        headers = auth_headers_supervisor
    res = await client.post(f"/api/v1/taller/{sid}/{operacion}", headers=headers, json=payload)
    assert res.status_code == 200, res.text
    revisiones = [d["estado_revision"] for d in res.json()["detalles"]]
    assert revisiones == (["APROBADA", "APROBADA"] if operacion == "tomar" else ["APROBADA", "PENDIENTE"])
    res = await client.post("/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"n_bus": "INICIAL-REV", "detalles": [{"nombre": "Reporte posterior"}]})
    assert res.status_code == 201, res.text
    assert res.json()["detalles"][-1]["estado_revision"] == "PENDIENTE"
    res = await client.post(f"/api/v1/taller/{sid}/tomar", headers=auth_headers_mecanico1, json={})
    assert res.status_code == 200, res.text
    assert res.json()["detalles"][-1]["estado_revision"] == "PENDIENTE"
