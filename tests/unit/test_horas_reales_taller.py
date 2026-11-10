from datetime import datetime, timedelta, timezone

import pytest

from app.modules.taller.utils import calcular_horas_reales_taller
from app.modules.supervision.services.supervision_service import SupervisionService

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize("estado", ["LIBERADO", "FINALIZADO"])
def test_cierre_congela_estadia_abierta(estado):
    solicitud = dict(estado=estado, fecha_cierre=NOW - timedelta(hours=5),
                     estadias=[dict(fecha_ingreso=NOW - timedelta(hours=8))])
    assert calcular_horas_reales_taller(solicitud, NOW) == 3
    assert calcular_horas_reales_taller(solicitud, NOW + timedelta(days=10)) == 3


@pytest.mark.parametrize("estado, esperado", [("PENDIENTE", 0), ("EN_REPARACION", 8), ("FINALIZADO", 0)])
def test_sin_visitas_no_usa_creacion(estado, esperado):
    solicitud = dict(estado=estado, fecha_creacion=NOW - timedelta(days=30),
                     fecha_primer_ingreso_taller=NOW - timedelta(hours=8))
    assert calcular_horas_reales_taller(solicitud, NOW) == esperado


def test_suma_visitas_cerradas_y_abierta_con_fechas_mixtas():
    solicitud = dict(estado="EN_REPARACION", horas_taller_acumuladas=999, estadias=[
        dict(horas_estadia=2),
        dict(fecha_ingreso=(NOW - timedelta(hours=10)).isoformat(), fecha_salida=NOW - timedelta(hours=7)),
        dict(fecha_ingreso=(NOW - timedelta(hours=1)).replace(tzinfo=None)),
    ])
    assert calcular_horas_reales_taller(solicitud, NOW) == 6


def test_resumen_dict_expone_horas_fisicas():
    dto = SupervisionService()._mapear_a_solicitud_resumen_dto(dict(
        id=1, estado="LIBERADO", fecha_creacion=NOW - timedelta(days=30),
        horas_taller_acumuladas=4,
    ))
    assert dto.tiempo_taller == dto.horas_en_taller == dto.horas_taller_acumuladas == 4


@pytest.mark.asyncio
async def test_total_sql_historial(db_session):
    from app.modules.buses.models.bus import Bus
    from app.modules.buses.repository.bus_repository import BusRepository
    from app.modules.taller.models.taller_solicitud import TallerSolicitud
    from app.modules.taller.models.taller_solicitud_estadia import TallerSolicitudEstadia
    bus = Bus(patente="TOTAL1", n_bus="TOTAL1")
    db_session.add(bus)
    await db_session.flush()
    ots = [TallerSolicitud(bus_id=bus.id, n_bus=bus.n_bus, es_ot=True, estado=estado,
                           horas_taller_acumuladas=horas)
           for estado, horas in [("FINALIZADO", 4), ("LIBERADO", 999), ("FINALIZADO", 0)]]
    db_session.add_all(ots)
    await db_session.flush()
    db_session.add(TallerSolicitudEstadia(solicitud_id=ots[1].id, numero_visita=1,
        fecha_ingreso=NOW - timedelta(hours=3), fecha_salida=NOW, horas_estadia=None))
    await db_session.flush()
    assert await BusRepository().get_horas_taller_totales(db_session, bus.id) == 7
