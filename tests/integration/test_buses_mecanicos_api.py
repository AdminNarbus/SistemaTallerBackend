from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, func, select

from app.core.exceptions import BusinessRuleException
from app.modules.buses.models.bus import Bus
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_estado_evento import TallerSolicitudEstadoEvento
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.repository.buses_taller_repository import BusesTallerRepository
from app.modules.taller.services.buses_taller_service import buses_taller_service


@pytest.fixture
async def bus_mecanico(db_session):
    bus = Bus(n_bus="MEC-100", patente="MEC-100", en_taller=False, is_active=True)
    db_session.add(bus)
    await db_session.commit()
    return bus


@pytest.mark.parametrize("autoasignar", [False, True, None])
async def test_falla_crea_ot_y_autoasigna_solo_si_se_solicita(
    client, db_session, bus_mecanico, auth_headers_mecanico1, autoasignar,
):
    bus_id = bus_mecanico.id
    payload = {"nombre": "Ruido en el motor"}
    if autoasignar is not None:
        payload["autoasignar"] = autoasignar

    response = await client.post(f"/api/v1/taller/buses/{bus_id}/fallas", json=payload, headers=auth_headers_mecanico1)

    assert response.status_code == 201, response.text
    ot = response.json()
    assert ot["bus_id"] == bus_id
    assert ot["usuario_creador_id"] == 2
    assert ot["estado"] == ("EN_REPARACION" if autoasignar else None)
    assert len(ot["detalles"]) == 1
    falla = ot["detalles"][0]
    assert falla["reportado_por_id"] == 2
    assert falla["estado"] == "PENDIENTE"
    assert [m["id"] for m in falla["mecanicos_asignados"]] == ([2] if autoasignar else [])
    await db_session.refresh(bus_mecanico)
    assert bus_mecanico.en_taller is bool(autoasignar)
    assert len(ot["estadias"]) == (1 if autoasignar else 0)
    assert any("Ruido en el motor" in comentario["comentario"] for comentario in ot["comentarios"])
    eventos = (await db_session.execute(select(TallerSolicitudEstadoEvento).order_by(TallerSolicitudEstadoEvento.id))).scalars().all()
    assert eventos[0].tipo_evento == "CREACION"
    assert eventos[0].usuario_actor_id == 2
    assert eventos[-1].estado_nuevo == (ot["estado"] or "PENDIENTE")
    assert ot["es_ot"] is bool(autoasignar)


@pytest.mark.parametrize("estado", ["PENDIENTE", "EN_REPARACION", "LIBERADO"])
@pytest.mark.parametrize("autoasignar", [False, True])
async def test_reutiliza_ot_vigente_incluida_liberada(
    client, db_session, bus_mecanico, auth_headers_mecanico1, estado, autoasignar,
):
    solicitud = TallerSolicitud(es_ot=True, n_bus=bus_mecanico.n_bus, bus_id=bus_mecanico.id, estado=estado)
    db_session.add(solicitud)
    await db_session.commit()
    solicitud_id = solicitud.id

    response = await client.post(
        f"/api/v1/taller/buses/{bus_mecanico.id}/fallas",
        json={"nombre": "Fuga detectada", "autoasignar": autoasignar}, headers=auth_headers_mecanico1,
    )

    assert response.status_code == 201, response.text
    assert response.json()["id"] == solicitud_id
    assert response.json()["estado"] == ("EN_REPARACION" if autoasignar else estado)
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitud)) == 1


async def test_ot_finalizada_se_conserva_y_abre_un_nuevo_ciclo(
    client, db_session, bus_mecanico, auth_headers_mecanico1,
):
    anterior = TallerSolicitud(es_ot=True, n_bus=bus_mecanico.n_bus, bus_id=bus_mecanico.id, estado="FINALIZADO")
    db_session.add(anterior)
    await db_session.commit()
    anterior_id = anterior.id

    response = await client.post(
        f"/api/v1/taller/buses/{bus_mecanico.id}/fallas",
        json={"nombre": "Nueva avería"}, headers=auth_headers_mecanico1,
    )

    assert response.status_code == 201, response.text
    assert response.json()["id"] != anterior_id
    await db_session.refresh(anterior)
    assert anterior.estado == "FINALIZADO"
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitud)) == 2


async def test_reutiliza_ot_historica_sin_bus_id(
    client, db_session, bus_mecanico, auth_headers_mecanico1,
):
    solicitud = TallerSolicitud(es_ot=True, n_bus=bus_mecanico.n_bus.lower(), estado="LIBERADO")
    db_session.add(solicitud)
    await db_session.commit()
    solicitud_id = solicitud.id

    response = await client.post(
        f"/api/v1/taller/buses/{bus_mecanico.id}/fallas", json={"nombre": "Otra falla"}, headers=auth_headers_mecanico1,
    )

    assert response.status_code == 201, response.text
    assert response.json()["id"] == solicitud_id
    assert response.json()["bus_id"] == bus_mecanico.id


async def test_error_al_agregar_falla_revierte_la_ot_nueva(
    client, db_session, bus_mecanico, auth_headers_mecanico1, monkeypatch,
):
    bus_id = bus_mecanico.id
    monkeypatch.setattr(buses_taller_service.averias, "registrar_falla", AsyncMock(side_effect=BusinessRuleException("Falla inválida")))

    response = await client.post(
        f"/api/v1/taller/buses/{bus_id}/fallas", json={"nombre": "Ruido"}, headers=auth_headers_mecanico1,
    )

    assert response.status_code == 422
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitud)) == 0
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitudEstadoEvento)) == 0


@pytest.mark.parametrize("payload, esperado", [
    ({}, 422), ({"nombre": "   "}, 422),
    ({"nombre": "Ruido", "mecanico_asignado_id": 3}, 422),
    ({"falla_id": 999999}, 422), ({"nombre": "Ruido", "categoria_id": 999999}, 422),
])
async def test_payload_invalido_no_crea_ot(client, db_session, bus_mecanico, auth_headers_mecanico1, payload, esperado):
    response = await client.post(f"/api/v1/taller/buses/{bus_mecanico.id}/fallas", json=payload, headers=auth_headers_mecanico1)
    assert response.status_code == esperado
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitud)) == 0


async def test_permisos_y_bus_inexistente_o_inactivo(
    client, db_session, bus_mecanico, auth_headers_mecanico1, auth_headers_conductor, auth_headers_supervisor,
):
    ruta = f"/api/v1/taller/buses/{bus_mecanico.id}/fallas"
    assert (await client.post(ruta, json={"nombre": "Ruido"})).status_code == 401
    for headers in (auth_headers_conductor, auth_headers_supervisor):
        assert (await client.post(ruta, json={"nombre": "Ruido"}, headers=headers)).status_code == 403
        assert (await client.get("/api/v1/taller/buses", headers=headers)).status_code == 403
    assert (await client.post("/api/v1/taller/buses/999999/fallas", json={"nombre": "Ruido"}, headers=auth_headers_mecanico1)).status_code == 404
    await db_session.refresh(bus_mecanico)
    bus_mecanico.is_active = False
    await db_session.commit()
    assert (await client.post(ruta, json={"nombre": "Ruido"}, headers=auth_headers_mecanico1)).status_code == 422


@pytest.fixture
async def flota_mecanicos(db_session):
    now = datetime.now(timezone.utc)
    for numero, estado in [("01", None), ("02", "FINALIZADO"), ("03", "LIBERADO"),
                           ("04", "EN_REPARACION"), ("05", "PENDIENTE"), ("06", "PENDIENTE")]:
        bus = Bus(n_bus=numero, patente=f"TEST-{numero}", is_active=True)
        db_session.add(bus)
        await db_session.flush()
        if estado:
            db_session.add(TallerSolicitud(es_ot=True, bus_id=bus.id, n_bus=numero, estado=estado, fecha_actualizacion=now))
    db_session.add(Bus(n_bus="00", patente="INACTIVO", is_active=False))
    await db_session.commit()


async def test_lista_buses_con_orden_global_y_sin_ot_finalizada(
    client, auth_headers_mecanico1, flota_mecanicos,
):
    response = await client.get("/api/v1/taller/buses", headers=auth_headers_mecanico1)
    assert response.status_code == 200, response.text
    buses = response.json()
    assert response.headers["X-Total-Count"] == "6"
    assert [bus["n_bus"] for bus in buses] == ["04", "05", "06", "03", "01", "02"]
    assert [bus["ot"]["estado"] for bus in buses[:4]] == ["EN_REPARACION", "PENDIENTE", "PENDIENTE", "LIBERADO"]
    assert all(bus["ot"] is None for bus in buses[4:])
    assert all(set(bus) == {"bus_id", "n_bus", "ot"} for bus in buses)


async def test_tarjeta_devuelve_creador_y_fecha_de_creacion_de_ot(
    client, db_session, bus_mecanico, auth_headers_mecanico1, seed_test_data,
):
    creacion = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    solicitud = TallerSolicitud(
        es_ot=True,
        bus_id=bus_mecanico.id, n_bus=bus_mecanico.n_bus, estado="PENDIENTE",
        usuario_creador_id=seed_test_data["conductor"].id,
        fecha_creacion=creacion, fecha_actualizacion=creacion + timedelta(days=9),
    )
    db_session.add(solicitud)
    await db_session.flush()
    db_session.add_all([
        TallerSolicitudDetalle(solicitud_id=solicitud.id, estado="PENDIENTE"),
        TallerSolicitudDetalle(solicitud_id=solicitud.id, estado="INCOMPLETA"),
        TallerSolicitudDetalle(solicitud_id=solicitud.id, estado="RESUELTA", resuelto=True),
    ])
    await db_session.commit()

    response = await client.get("/api/v1/taller/buses", headers=auth_headers_mecanico1)

    assert response.status_code == 200, response.text
    tarjeta = response.json()[0]
    assert set(tarjeta) == {"bus_id", "n_bus", "ot"}
    ot = tarjeta["ot"]
    assert set(ot) == {"id", "es_ot", "estado", "creador_nombre", "fecha_creacion", "numero_fallas_pendientes"}
    assert ot["id"] == solicitud.id
    assert ot["creador_nombre"] == "Juan Conductor"
    assert ot["fecha_creacion"].startswith("2026-10-20T12:00:00")
    assert ot["numero_fallas_pendientes"] == 2
    assert ot["estado"] == "PENDIENTE"


@pytest.mark.parametrize("skip, cantidad", [(0, 2), (2, 2), (4, 2), (20, 0)])
async def test_paginacion_con_total_incluso_fuera_de_rango(
    client, auth_headers_mecanico1, flota_mecanicos, skip, cantidad,
):
    response = await client.get(f"/api/v1/taller/buses?limit=2&skip={skip}", headers=auth_headers_mecanico1)
    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"] == "6"
    assert len(response.json()) == cantidad


async def test_busqueda_inactivos_y_lista_vacia(client, auth_headers_mecanico1, flota_mecanicos):
    response = await client.get("/api/v1/taller/buses?q=TEST-03", headers=auth_headers_mecanico1)
    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"] == "1"
    assert response.json()[0]["n_bus"] == "03"
    inactivos = await client.get("/api/v1/taller/buses?solo_activos=false", headers=auth_headers_mecanico1)
    assert inactivos.headers["X-Total-Count"] == "7"
    vacia = await client.get("/api/v1/taller/buses?q=inexistente", headers=auth_headers_mecanico1)
    assert vacia.status_code == 200, vacia.text
    assert vacia.json() == []
    assert vacia.headers["X-Total-Count"] == "0"


async def test_listado_usa_una_consulta_y_cuenta_fallas_sin_duplicar_bus(db_session):
    bus = Bus(n_bus="LEGACY", patente="LEG-001", is_active=True)
    db_session.add(bus)
    await db_session.flush()
    activa = TallerSolicitud(es_ot=True, n_bus="legacy", estado="LIBERADO")
    finalizada = TallerSolicitud(es_ot=True, n_bus=bus.n_bus, bus_id=bus.id, estado="FINALIZADO")
    db_session.add_all([activa, finalizada])
    await db_session.flush()
    db_session.add_all([
        TallerSolicitudDetalle(solicitud_id=activa.id, estado="PENDIENTE"),
        TallerSolicitudDetalle(solicitud_id=activa.id, estado="INCOMPLETA"),
        TallerSolicitudDetalle(solicitud_id=activa.id, estado="RESUELTA", resuelto=True),
    ])
    await db_session.commit()
    activa_id = activa.id
    consultas = []
    def contar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    event.listen(db_session.bind.sync_engine, "before_cursor_execute", contar)
    try:
        filas = await BusesTallerRepository().listar(db_session, {"skip": 0, "limit": 20, "q": None, "solo_activos": True})
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", contar)
    assert len(consultas) == 1
    assert len(filas) == 1
    assert filas[0]["ot_id"] == activa_id
    assert filas[0]["numero_fallas_pendientes"] == 2
    assert filas[0]["total"] == 1
