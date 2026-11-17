from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.core.exceptions import BusinessRuleException, PermissionException
from app.modules.taller.dtos import AgregarFallaDTO
from app.modules.taller.services.averias_service import resolver_fecha_reporte


@pytest.mark.parametrize("rol", ["SUPERVISOR", "ADMIN", "MECANICO", "CONDUCTOR"])
def test_reporte_sin_fecha_conserva_momento_actual(rol):
    ahora = datetime.now(timezone.utc)
    dto = AgregarFallaDTO(nombre="Frenos")

    resultado = resolver_fecha_reporte(dto, rol, ahora)

    assert resultado == ahora


@pytest.mark.parametrize("rol", ["SUPERVISOR", "ADMIN"])
def test_reporte_historico_normaliza_zona_horaria(rol):
    ahora = datetime(2026, 11, 12, 15, tzinfo=timezone.utc)
    dto = AgregarFallaDTO(fecha_reporte="2026-11-10T09:30:00-03:00")

    resultado = resolver_fecha_reporte(dto, rol, ahora)

    assert resultado == datetime(2026, 11, 10, 12, 30, tzinfo=timezone.utc)
    assert resultado.tzinfo is timezone.utc


@pytest.mark.parametrize("rol", ["MECANICO", "CONDUCTOR", ""])
def test_fecha_explicita_exige_supervision(rol):
    ahora = datetime.now(timezone.utc)
    dto = AgregarFallaDTO(fecha_reporte=ahora - timedelta(days=1))

    with pytest.raises(PermissionException, match="Solo supervisores"):
        resolver_fecha_reporte(dto, rol, ahora)


def test_reporte_rechaza_futuro():
    ahora = datetime.now(timezone.utc)
    dto = AgregarFallaDTO(fecha_reporte=ahora + timedelta(seconds=1))

    with pytest.raises(BusinessRuleException, match="futura"):
        resolver_fecha_reporte(dto, "SUPERVISOR", ahora)


def test_reporte_permite_instante_actual():
    ahora = datetime.now(timezone.utc)
    dto = AgregarFallaDTO(fecha_reporte=ahora)

    resultado = resolver_fecha_reporte(dto, "SUPERVISOR", ahora)

    assert resultado == ahora


@pytest.mark.parametrize("fecha", ["2026-11-10", "2026-11-10T09:30:00", "invalida"])
def test_reporte_exige_fecha_con_zona_horaria(fecha):
    with pytest.raises(ValidationError):
        AgregarFallaDTO(fecha_reporte=fecha)
