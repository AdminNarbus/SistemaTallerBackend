"""Reglas puras del módulo preventivo."""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from app.core.exceptions import BusinessRuleException
from app.modules.control_mantenciones.dtos.contracts import Borrador, FilaBorrador
from app.modules.control_mantenciones.services.domain import (
    desplazar_mes,
    estado_km,
    fecha_valida,
    hoy,
    intervalo,
    proyectar,
)
from app.modules.control_mantenciones.services.imports import ImportService, leer_excel


@pytest.mark.parametrize(
    "marca,bus,esperado",
    [
        ("Scania", "356", 50000),
        ("Volvo", "386", 40000),
        ("Mercedes", "354", 40000),
        ("Mercedes", "396", 40000),
        ("Mercedes", "428", 60000),
        ("desconocida", "1", None),
    ],
)
def test_intervalos(marca, bus, esperado):
    # Arrange / Act / Assert
    assert intervalo(marca, bus, None) == esperado
    assert intervalo(marca, bus, Decimal(12345)) == 12345


@pytest.mark.parametrize(
    "km,estado",
    [
        (None, "Sin datos suficientes para calcular"),
        (0, "Vencida"),
        (-1, "Vencida"),
        (5000, "Crítica"),
        (5001, "Próxima"),
        (25000, "Próxima"),
        (25001, "Al día"),
    ],
)
def test_umbrales(km, estado):
    assert estado_km(km) == estado


def test_fechas_y_meses():
    assert fecha_valida("2026-02-30") is None
    assert desplazar_mes(fecha_valida("2026-08-31"), -6).isoformat() == "2026-02-28"


def test_proyeccion():
    # Arrange
    fecha = hoy()
    ficha = {
        "conflicto": False,
        "sin_lectura_reciente": False,
        "restantes": Decimal(1000),
        "ultima_lectura": fecha,
    }
    registros = [
        {
            "fecha": fecha - timedelta(days=d),
            "kilometraje": Decimal(10000 - d * 100),
            "estado": "aceptado",
        }
        for d in [14, 7, 0]
    ]
    # Act
    resultado = proyectar(registros, ficha)
    # Assert
    assert resultado["dias"] == 10
    registros.append({"estado": "pendiente"})
    assert not proyectar(registros, ficha)["disponible"]


def test_excel_ignora_hora():
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Query result"
    hoja.append(["n_bus", "fecha", "hora", "odometro"])
    hoja.append([354, "01-10-2026", "hora inválida", 123456])
    buffer = BytesIO()
    libro.save(buffer)
    borrador = leer_excel("semana.xlsx", buffer.getvalue())
    assert borrador.filas[0].fecha == "2026-10-01"
    assert "hora" not in borrador.filas[0].model_dump()
    with pytest.raises(BusinessRuleException):
        leer_excel("archivo.xlsx", b"no es excel")


async def test_revision_servicio_sin_escrituras():
    # Arrange
    db = AsyncMock()
    servicio = ImportService(db, 1)
    servicio.repo.buses = AsyncMock(return_value=[])
    servicio.repo.contexto = AsyncMock(return_value={})
    servicio.repo.duplicados = AsyncMock(return_value=set())
    borrador = Borrador(
        nombre_archivo="semana.xlsx",
        filas=[
            FilaBorrador(
                fila=2, numero_bus="999", fecha="2026-10-01", kilometraje="100"
            )
        ],
    )
    # Act
    revision = await servicio.revisar(borrador)
    # Assert
    assert revision.resultados[0].estado == "pendiente"
    db.commit.assert_not_awaited()
    db.flush.assert_not_awaited()
    db.execute.assert_not_awaited()

@pytest.mark.parametrize(
    "dias,nuevo,estado",
    [
        (1, "542000", "aceptado"),
        (1, "542000.01", "pendiente"),
        (3, "546000", "aceptado"),
        (6, "550000.01", "pendiente"),
        (7, "550000", "aceptado"),
        (7, "550000.01", "pendiente"),
        (7, "1300000", "pendiente"),
        (8, "552000", "aceptado"),
        (14, "560000.01", "pendiente"),
        (None, "1300000", "aceptado"),
    ],
)
def test_revision_excel_detecta_aumentos_excesivos(dias, nuevo, estado):
    servicio = ImportService(AsyncMock(), 1)
    fecha = hoy() - timedelta(days=1)
    fila = FilaBorrador(
        fila=2, numero_bus="354", fecha=fecha.isoformat(), kilometraje=nuevo
    )
    anterior = (
        {"anterior_fecha": fecha - timedelta(days=dias), "anterior_km": Decimal("540000")}
        if dias is not None
        else {}
    )
    contexto = {
        "buses": {"354": 1},
        "indices": {fila.id: 0},
        "contextos": {0: anterior},
        "por_fecha": {},
        "duplicados": set(),
    }

    resultado = servicio.resultado(fila, contexto)

    assert resultado.estado == estado
    assert servicio.estado_confirmado(resultado) == estado
    if estado == "pendiente":
        assert len(resultado.motivos) == 1
        assert "límite posible" in resultado.motivos[0]
        assert not any(caracter.isdigit() for caracter in resultado.motivos[0])
    else:
        assert resultado.motivos == []
