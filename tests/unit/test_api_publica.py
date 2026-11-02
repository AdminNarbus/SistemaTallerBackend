from datetime import datetime, timezone
from app.api.publica.router import BusTallerPublicoDTO, SolicitudPublicaDTO, router


def test_solicitud_publica_y_rutas():
    dto = SolicitudPublicaDTO(id=1, n_bus="10", es_ot=False, estado="PENDIENTE", fecha_creacion=datetime.now(timezone.utc))
    assert set(dto.model_dump()) == {"id", "n_bus", "es_ot", "estado", "descripcion_general", "fecha_creacion", "fecha_actualizacion"}
    assert dto.estado is None
    assert {route.path for route in router.routes} == {"/publica/solicitudes", "/publica/buses-en-taller"}
    bus = BusTallerPublicoDTO(id=1, n_bus=None, patente="ABCD12", marca=None, modelo=None, en_taller=True)
    assert set(bus.model_dump()) == {"id", "n_bus", "patente", "marca", "modelo", "en_taller"}
