from datetime import datetime, timedelta, timezone

import pytest

from app.modules.buses.models.bus import Bus
from app.modules.supervision.services import supervision_service
from app.modules.taller.dtos import SolicitudCreateDTO, SolicitudDetalleCreateDTO, TomarTrabajoDTO
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.services.mappers import dict_to_solicitud_dto, dict_to_solicitud_resumen_dto
from app.modules.taller.services.taller_service import taller_service


@pytest.mark.asyncio
@pytest.mark.parametrize("rol", ["SUPERVISOR", "ADMIN"])
@pytest.mark.parametrize("ingreso", [{}, {"ingreso_inmediato_taller": None}, {"ingreso_inmediato_taller": False}])
async def test_reportar_no_registra_visita_y_alerta_hasta_ingreso_real(
    db_session, seed_test_data, rol, ingreso
):
    bus = Bus(n_bus="391", patente="TEST-391", is_active=True, en_taller=False)
    db_session.add(bus)
    await db_session.commit()
    supervisor = seed_test_data["supervisor"]
    creada = await taller_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(
            bus_id=bus.id,
            detalles=[SolicitudDetalleCreateDTO(falla_id=seed_test_data["falla1"].id)],
            **ingreso,
        ),
        creador_id=supervisor.id,
        creador_nombre=supervisor.nombre_completo,
        creador_rol=rol,
    )
    await db_session.refresh(bus)
    assert bus.en_taller is False
    assert creada.estadias == []
    assert creada.total_visitas == 0
    assert creada.fecha_primer_ingreso_taller is None
    assert creada.horas_demora_primer_ingreso is None
    assert creada.horas_en_taller == 0.0

    # La edad de la OT sirve para la alerta de demora, nunca para horas en taller.
    solicitud = await db_session.get(TallerSolicitud, creada.id)
    solicitud.fecha_creacion = datetime.now(timezone.utc) - timedelta(hours=72)
    await db_session.commit()
    ficha = await taller_service.get_solicitud(db_session, creada.id)
    assert ficha.horas_en_taller == 0.0
    assert ficha.horas_taller_acumuladas == 0.0
    assert ficha.total_visitas == 0
    resumenes = await supervision_service.get_auditoria_solicitudes(db_session)
    assert next(r for r in resumenes if r.id == creada.id).tiempo_taller == pytest.approx(72.0, abs=0.1)
    assert supervision_service._mapear_orm_a_auditoria_dto(solicitud).horas_en_taller == 0.0
    alertas = await supervision_service.get_alertas_taller(db_session)
    assert any(a.solicitud_id == creada.id and a.tipo == "OT_SIN_INGRESO_TALLER" for a in alertas)

    # Comenzar la reparación sí registra el primer ingreso y su demora real.
    atendida = await taller_service.tomar_trabajo(
        db_session, creada.id, seed_test_data["mecanico1"].id, TomarTrabajoDTO()
    )
    await db_session.refresh(bus)
    assert bus.en_taller is True
    assert atendida.total_visitas == 1
    assert atendida.fecha_primer_ingreso_taller is not None
    assert atendida.horas_demora_primer_ingreso == pytest.approx(72.0, abs=0.1)
    assert atendida.horas_en_taller == 0.0
    assert atendida.estadias[0].fecha_salida is None
    alertas = await supervision_service.get_alertas_taller(db_session)
    assert not any(a.solicitud_id == creada.id and a.tipo == "OT_SIN_INGRESO_TALLER" for a in alertas)


def test_filas_postgres_sin_visitas_no_usan_antiguedad_como_tiempo_taller():
    fila = {
        "id": 43, "n_bus": "391", "estado": "PENDIENTE",
        "fecha_creacion": datetime.now(timezone.utc) - timedelta(days=8),
        "horas_en_taller": 192.0, "estadias_json": [],
    }
    assert dict_to_solicitud_dto(fila).horas_en_taller == 0.0
    assert dict_to_solicitud_resumen_dto(fila).tiempo_taller == pytest.approx(192.0, abs=0.1)
    assert supervision_service._mapear_dict_a_solicitud_resumen_dto(fila).tiempo_taller == pytest.approx(192.0, abs=0.1)
    assert supervision_service._mapear_dict_a_auditoria_dto(fila).horas_en_taller == 0.0


def test_filas_postgres_suman_visitas_cerradas_y_abierta_sin_contar_espera():
    now = datetime.now(timezone.utc)
    fila = {
        "id": 3, "n_bus": "377", "estado": "EN_REPARACION",
        "fecha_creacion": now - timedelta(days=8), "horas_en_taller": 192.0,
        "estadias_json": [
            {"numero_visita": 1, "fecha_ingreso": now - timedelta(days=3),
             "fecha_salida": now - timedelta(days=3) + timedelta(hours=6), "horas_estadia": 6.0},
            {"numero_visita": 2, "fecha_ingreso": now - timedelta(hours=2)},
        ],
    }
    ficha = dict_to_solicitud_dto(fila)
    assert ficha.total_visitas == 2
    assert ficha.horas_en_taller == pytest.approx(8.0, abs=0.1)
    assert dict_to_solicitud_resumen_dto(fila).tiempo_taller == pytest.approx(192.0, abs=0.1)
    assert supervision_service._mapear_dict_a_auditoria_dto(fila).horas_en_taller == pytest.approx(8.0, abs=0.1)
