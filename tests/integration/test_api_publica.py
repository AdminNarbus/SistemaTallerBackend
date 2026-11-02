import pytest
from app.core.config import settings
from app.modules.buses.models.bus import Bus
from app.modules.taller.models.taller_solicitud import TallerSolicitud


@pytest.mark.asyncio
async def test_consultas_publicas(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", True)
    db_session.add_all([
        Bus(id=1, patente="AAAA11", n_bus="1", en_taller=True),
        Bus(id=2, patente="BBBB22", n_bus="2", en_taller=False),
        TallerSolicitud(id=1, n_bus="1", bus_id=1, es_ot=False, estado="PENDIENTE"),
        TallerSolicitud(id=2, n_bus="2", bus_id=2, es_ot=True, estado="FINALIZADO"),
    ])
    await db_session.commit()
    base = f"{settings.API_V1_STR}/publica"
    response = await client.get(f"{base}/solicitudes")
    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"] == "2"
    solicitudes = response.json()
    assert len(solicitudes) == 2
    assert set(solicitudes[0]) == {"id", "n_bus", "es_ot", "estado", "descripcion_general", "fecha_creacion", "fecha_actualizacion"}
    assert solicitudes[0]["es_ot"] is False and solicitudes[0]["estado"] is None
    assert solicitudes[1]["es_ot"] is True and solicitudes[1]["estado"] == "FINALIZADO"
    assert (await client.get(f"{base}/solicitudes/2")).status_code == 404
    buses = await client.get(f"{base}/buses-en-taller")
    assert buses.status_code == 200
    assert buses.headers["X-Total-Count"] == "1"
    assert [bus["id"] for bus in buses.json()] == [1]
    assert set(buses.json()[0]) == {"id", "n_bus", "patente", "marca", "modelo", "en_taller"}
    assert (await client.get(f"{base}/buses-en-taller", params={"limit": 101})).status_code == 422
