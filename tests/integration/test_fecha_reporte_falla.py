from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.modules.auth.models.usuario import Usuario
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle


def fecha_utc(valor):
    fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    return fecha.replace(tzinfo=timezone.utc) if fecha.tzinfo is None else fecha.astimezone(timezone.utc)


@pytest.fixture
async def ot_para_reporte(client, auth_headers_conductor, auth_headers_supervisor):
    respuesta = await client.post("/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"n_bus": "FECHA-REPORTE", "detalles": [{"nombre": "Falla inicial"}]})
    assert respuesta.status_code == 201, respuesta.text
    solicitud_id = respuesta.json()["id"]
    respuesta = await client.post(f"/api/v1/taller/{solicitud_id}/aprobar",
        headers=auth_headers_supervisor, json={})
    assert respuesta.status_code == 200, respuesta.text
    return solicitud_id


@pytest.mark.parametrize("opciones", [{}, {"mecanico_asignado_id": 2},
    {"resuelto": True, "mecanico_resolvio_id": 2}])
async def test_supervision_guarda_reporte_historico_sin_retroceder_auditoria(
    client, ot_para_reporte, auth_headers_supervisor, opciones,
):
    inicio = datetime.now(timezone.utc)
    reporte = inicio - timedelta(days=7)
    url = f"/api/v1/supervision/solicitudes/{ot_para_reporte}/detalles"

    respuesta = await client.post(url, headers=auth_headers_supervisor,
        json={"nombre": "Falla histórica", "fecha_reporte": reporte.isoformat(), **opciones})

    assert respuesta.status_code == 201, respuesta.text
    nueva = respuesta.json()["detalles"][-1]
    assert fecha_utc(nueva["fecha_reporte"]) == reporte
    assert fecha_utc(nueva["fecha_creacion"]) >= inicio
    assert fecha_utc(nueva["fecha_revision"]) >= inicio
    assert nueva["reportado_por_id"] == 4
    assert fecha_utc(respuesta.json()["fecha_actualizacion"]) >= inicio
    if opciones.get("resuelto"):
        assert fecha_utc(nueva["fecha_resolucion"]) >= inicio
    if opciones.get("mecanico_asignado_id"):
        assert fecha_utc(nueva["historial_asignaciones"][0]["fecha_asignacion"]) >= inicio

    ficha = await client.get(f"/api/v1/taller/{ot_para_reporte}", headers=auth_headers_supervisor)
    assert ficha.status_code == 200, ficha.text
    guardada = next(d for d in ficha.json()["detalles"] if d["id"] == nueva["id"])
    assert fecha_utc(guardada["fecha_reporte"]) == reporte
    evento = next(e for e in guardada["historial_eventos"] if e["tipo_evento"] == "REPORTADA")
    assert fecha_utc(evento["fecha_evento"]) == reporte
    # SQLite almacena el default de auditoría con precisión de segundos.
    assert fecha_utc(evento["fecha_registro"]) >= inicio.replace(microsecond=0)


@pytest.mark.parametrize("fecha", ["omitida", None])
async def test_fecha_opcional_conserva_comportamiento_anterior(
    client, ot_para_reporte, auth_headers_supervisor, fecha,
):
    payload = {"nombre": "Reporte actual"}
    if fecha is None:
        payload["fecha_reporte"] = None

    respuesta = await client.post(f"/api/v1/supervision/solicitudes/{ot_para_reporte}/detalles",
        headers=auth_headers_supervisor, json=payload)

    assert respuesta.status_code == 201, respuesta.text
    nueva = respuesta.json()["detalles"][-1]
    assert fecha_utc(nueva["fecha_reporte"]) == fecha_utc(nueva["fecha_creacion"])


@pytest.mark.parametrize("fecha", ["futura", "2026-11-10", "2026-11-10T09:30:00", "invalida"])
async def test_fecha_invalida_no_crea_falla(
    client, db_session, ot_para_reporte, auth_headers_supervisor, fecha,
):
    if fecha == "futura":
        fecha = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    respuesta = await client.post(f"/api/v1/supervision/solicitudes/{ot_para_reporte}/detalles",
        headers=auth_headers_supervisor, json={"nombre": "No guardar", "fecha_reporte": fecha})

    assert respuesta.status_code == 422, respuesta.text
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitudDetalle)) == 1


async def test_mecanico_no_puede_indicar_fecha_en_ruta_compartida(
    client, db_session, ot_para_reporte, auth_headers_mecanico1,
):
    respuesta = await client.post(f"/api/v1/taller/{ot_para_reporte}/detalles",
        headers=auth_headers_mecanico1,
        json={"nombre": "No guardar", "fecha_reporte": "2026-11-10T09:30:00-03:00"})

    assert respuesta.status_code == 403, respuesta.text
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitudDetalle)) == 1


async def test_admin_puede_indicar_reporte_con_offset(
    client, db_session, ot_para_reporte,
):
    db_session.add(Usuario(id=6, nombre="Ana", apellido="Admin", username="admin-fecha",
        password_hash="sin-login", rol_id=4, is_active=True))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(subject=6)}"}

    respuesta = await client.post(f"/api/v1/supervision/solicitudes/{ot_para_reporte}/detalles",
        headers=headers, json={"nombre": "Histórica admin", "fecha_reporte": "2026-11-10T09:30:00-03:00"})

    assert respuesta.status_code == 201, respuesta.text
    nueva = respuesta.json()["detalles"][-1]
    assert fecha_utc(nueva["fecha_reporte"]) == datetime(2026, 11, 10, 12, 30, tzinfo=timezone.utc)
    assert nueva["reportado_por_id"] == 6


async def test_supervision_crea_solicitud_con_fechas_notificacion_distintas(
    client, auth_headers_supervisor,
):
    inicio = datetime.now(timezone.utc)
    fecha1 = inicio - timedelta(days=5)
    fecha2 = inicio - timedelta(days=2)

    respuesta = await client.post(
        "/api/v1/formularios/mantencion/solicitudes",
        headers=auth_headers_supervisor,
        json={
            "n_bus": "SOL-FECHA",
            "detalles": [
                {"nombre": "Fuga neumática", "fecha_reporte": fecha1.isoformat()},
                {"nombre": "Espejo roto", "fecha_reporte": fecha2.isoformat()},
            ],
        },
    )

    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    detalles = datos["detalles"]
    assert len(detalles) == 2
    assert fecha_utc(detalles[0]["fecha_reporte"]) == fecha1
    assert fecha_utc(detalles[1]["fecha_reporte"]) == fecha2
    assert fecha_utc(detalles[0]["fecha_creacion"]) >= inicio
    assert fecha_utc(detalles[1]["fecha_creacion"]) >= inicio

    ficha = await client.get(f"/api/v1/taller/{datos['id']}", headers=auth_headers_supervisor)
    assert ficha.status_code == 200, ficha.text
    for idx, esperado in enumerate([fecha1, fecha2]):
        det_ficha = ficha.json()["detalles"][idx]
        ev = next(e for e in det_ficha["historial_eventos"] if e["tipo_evento"] == "REPORTADA")
        assert fecha_utc(ev["fecha_evento"]) == esperado


async def test_conductor_no_puede_enviar_fecha_reporte_al_crear_solicitud(
    client, auth_headers_conductor,
):
    ayer = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    respuesta = await client.post(
        "/api/v1/formularios/mantencion/solicitudes",
        headers=auth_headers_conductor,
        json={
            "n_bus": "COND-FECHA",
            "detalles": [{"nombre": "Falla chofer", "fecha_reporte": ayer}],
        },
    )
    assert respuesta.status_code == 403, respuesta.text


async def test_supervision_edita_fecha_notificacion_solo_en_falla_abierta(
    client, ot_para_reporte, auth_headers_supervisor, taller_resultado,
):
    ficha_ini = await client.get(f"/api/v1/taller/{ot_para_reporte}", headers=auth_headers_supervisor)
    assert ficha_ini.status_code == 200
    det_inicial = ficha_ini.json()["detalles"][0]
    creacion_original = fecha_utc(det_inicial["fecha_creacion"])
    nueva_fecha = datetime.now(timezone.utc) - timedelta(days=3)

    res_edit = await client.patch(
        f"/api/v1/supervision/solicitudes/{ot_para_reporte}/detalles/{det_inicial['id']}",
        headers=auth_headers_supervisor,
        json={
            "descripcion_personalizada": det_inicial["descripcion_personalizada"],
            "fecha_reporte": nueva_fecha.isoformat(),
        },
    )
    assert res_edit.status_code == 200, res_edit.text
    editado = next(d for d in res_edit.json()["detalles"] if d["id"] == det_inicial["id"])
    assert fecha_utc(editado["fecha_reporte"]) == nueva_fecha
    assert fecha_utc(editado["fecha_creacion"]) == creacion_original
    ev_reportada = next(e for e in editado["historial_eventos"] if e["tipo_evento"] == "REPORTADA")
    assert fecha_utc(ev_reportada["fecha_evento"]) == nueva_fecha

    # Marcar la falla como RESUELTA y verificar que ya no permite modificar fecha_reporte
    body_resolver = await taller_resultado["payload"](ot_para_reporte, det_inicial["id"], "RESUELTA")
    res_resolver = await client.patch(
        f"/api/v1/supervision/solicitudes/{ot_para_reporte}/detalles/{det_inicial['id']}/resolver",
        headers=auth_headers_supervisor,
        json=body_resolver,
    )
    assert res_resolver.status_code == 200, res_resolver.text

    otra_fecha = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    res_edit_resuelta = await client.patch(
        f"/api/v1/supervision/solicitudes/{ot_para_reporte}/detalles/{det_inicial['id']}",
        headers=auth_headers_supervisor,
        json={
            "descripcion_personalizada": "No debe cambiar",
            "fecha_reporte": otra_fecha,
        },
    )
    assert res_edit_resuelta.status_code == 422, res_edit_resuelta.text
