import json
from types import SimpleNamespace

from app.core.config import settings
from app.modules.supervision.dtos.telegram_dto import TelegramNotificacionDTO
from app.modules.supervision.services.telegram_client import construir_mensaje
from app.modules.taller.services.telegram_solicitud_service import encolar_reporte


def test_solicitud_incluye_siete_fallas(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_SOLICITUDES_DESTINATARIOS", "-123")
    registros = []
    db = SimpleNamespace(add=registros.append)
    solicitud = SimpleNamespace(id=123, n_bus="123")
    dto = SimpleNamespace(descripcion_general=None)
    detalles = [(None, None, None, None, f"Falla {n}") for n in range(1, 8)]

    encolar_reporte(db, solicitud, ("Chofer", dto, detalles))

    parametros = json.loads(registros[0].mensaje)
    envio = TelegramNotificacionDTO(clave=registros[0].clave, solicitud_id=123,
        tipo="SOLICITUD_CHOFER", severidad="INFO", destinatario="-123",
        mensaje=registros[0].mensaje, parametros=parametros)
    mensaje = construir_mensaje(envio)
    assert all(f"• Falla {n}" in mensaje for n in range(1, 8))


def test_solicitud_larga_avisa_que_hay_mas_detalles(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_SOLICITUDES_DESTINATARIOS", "-123")
    registros = []
    db = SimpleNamespace(add=registros.append)
    detalles = [(None, None, None, None, "x" * 1000) for _ in range(7)]
    encolar_reporte(db, SimpleNamespace(id=1, n_bus="Bus"),
        ("Chofer", SimpleNamespace(descripcion_general=None), detalles))
    fallas = json.loads(registros[0].mensaje)[3]
    assert len(fallas) <= 3400
    assert "Hay más detalles en el sistema de taller" in fallas
