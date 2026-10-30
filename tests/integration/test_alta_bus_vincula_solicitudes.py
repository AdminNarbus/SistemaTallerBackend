"""El alta de flota genera ID y recupera solicitudes creadas antes del catálogo."""

import pytest
from sqlalchemy import select

from app.modules.buses.models.bus import Bus
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from scripts.reparar_bus_prueba_uno import reparar_ot_prueba


@pytest.mark.asyncio
async def test_alta_bus_genera_id_vincula_ot_y_aparece_a_mecanicos(
    client, db_session, auth_headers_supervisor, auth_headers_conductor, auth_headers_mecanico1,
):
    # Arrange: el ID 1 pertenece al 354; existe una solicitud antigua del número 1.
    db_session.add(Bus(id=1, n_bus="354", patente="REAL-354", is_active=True))
    await db_session.commit()
    solicitud = await client.post(
        "/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"n_bus": "1", "detalles": [{"nombre": "Falla de prueba"}]},
    )
    assert solicitud.status_code == 201, solicitud.text
    ot_id = solicitud.json()["id"]
    assert solicitud.json()["bus_id"] is None

    # Act: el endpoint normal de alta genera y devuelve su propio ID.
    alta = await client.post(
        "/api/v1/buses", headers=auth_headers_supervisor,
        json={"n_bus": "1", "patente": "TEST-BUS-1"},
    )
    assert alta.status_code == 201, alta.text
    bus_id = alta.json()["id"]

    # Assert: vínculo persistido, tarjeta visible y reutilización de la misma OT.
    assert bus_id != 1
    db_session.expire_all()
    assert (await db_session.get(TallerSolicitud, ot_id)).bus_id == bus_id
    tarjetas = await client.get("/api/v1/taller/buses?q=1", headers=auth_headers_mecanico1)
    assert tarjetas.status_code == 200, tarjetas.text
    tarjeta = next(b for b in tarjetas.json() if b["n_bus"] == "1")
    assert tarjeta["bus_id"] == bus_id
    assert tarjeta["ot"]["id"] == ot_id
    nueva_falla = await client.post(
        "/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"bus_id": bus_id, "detalles": [{"nombre": "Segunda falla"}]},
    )
    assert nueva_falla.status_code == 201, nueva_falla.text
    assert nueva_falla.json()["id"] == ot_id
    assert len(nueva_falla.json()["detalles"]) == 2
    assert (await db_session.get(Bus, 1)).n_bus == "354"


@pytest.mark.asyncio
async def test_reparacion_prueba_es_idempotente_y_no_reasigna_bus_real(db_session):
    # Arrange: solo existe el bus real 354 y la OT artificial sin FK.
    db_session.add(Bus(id=1, n_bus="354", patente="REAL-354", is_active=True))
    ot = TallerSolicitud(id=35, n_bus="1", descripcion_general="test. Bus 1 ficticio; PRUEBA ARTIFICIAL", estado="PENDIENTE")
    db_session.add(ot)
    await db_session.commit()

    # Act: repetir la reparación no crea dos vehículos.
    primero = await reparar_ot_prueba(db_session)
    await db_session.commit()
    segundo = await reparar_ot_prueba(db_session)
    await db_session.commit()

    # Assert: la secuencia genera el ID y la OT queda asociada al ficticio.
    assert primero == segundo
    assert primero != 1
    assert ot.bus_id == primero
    buses = (await db_session.scalars(select(Bus).where(Bus.n_bus == "1"))).all()
    assert len(buses) == 1
    assert buses[0].patente == "TEST-BUS-1"
    assert (await db_session.get(Bus, 1)).n_bus == "354"
