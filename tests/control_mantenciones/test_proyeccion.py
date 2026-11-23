"""Pruebas focalizadas de la proyección del Control de Mantenciones."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.modules.control_mantenciones.services.domain import proyectar
from app.modules.control_mantenciones.services.queries import QueryService

FECHA = date(2026, 11, 11)
FALLO = {"disponible": False, "mensaje": "Sin datos suficientes para estimar"}


def registro(dias_atras, kilometraje, tipo="kilometraje", **extras):
    return {
        "fecha": FECHA - timedelta(days=dias_atras),
        "kilometraje": Decimal(kilometraje),
        "tipo": tipo,
        "estado": "aceptado",
        **extras,
    }


def ficha(**cambios):
    return {
        "conflicto": False,
        "sin_lectura_reciente": False,
        "restantes": Decimal(18171),
        "ultima_lectura": FECHA,
        "proxima_mantencion": Decimal(1430091),
        **cambios,
    }


def registros_354():
    return [
        registro(75, 1398210),
        registro(57, 1403565),
        registro(10, 1406248),
        registro(3, 1410070),
        registro(0, 1411920),
    ]


def test_proyeccion_bus_354_usa_el_aumento_sostenido():
    assert proyectar(registros_354(), ficha()) == {
        "disponible": True,
        "promedio_diario": Decimal("567.20"),
        "dias": 33,
        "fecha": date(2026, 12, 14),
        "ventana_dias": 90,
    }


def test_un_tramo_rapido_no_desplaza_la_mediana():
    lecturas = [
        registro(30, 10000),
        registro(28, 10200),
        registro(21, 10900),
        registro(14, 12300),
        registro(7, 13000),
        registro(0, 15800),
    ]
    # Solo cuentan los últimos cuatro ritmos: 100, 200, 100 y 400.
    assert proyectar(lecturas, ficha())["promedio_diario"] == Decimal(150)


@pytest.mark.parametrize(
    "registros, tasa",
    [
        (
            [registro(14, 10000, "mantencion"), registro(7, 11400), registro(0, 12100)],
            Decimal(150),
        ),
        (
            [registro(14, 10000, "mantencion"), registro(7, 11400), registro(3, 11400),
             registro(0, 11400)],
            Decimal(100),
        ),
        (
            [registro(14, 10000), registro(10, 10400), registro(7, 11500, "mantencion"),
             registro(7, 11500, interpolado=True), registro(0, 12400), registro(0, 12400)],
            (Decimal(100) + Decimal(2000) / 10) / 2,
        ),
    ],
)
def test_proyeccion_respaldo_y_registros_excluidos(registros, tasa):
    assert proyectar(registros, ficha())["promedio_diario"] == tasa


@pytest.mark.parametrize(
    "cambios",
    [{"conflicto": True}, {"sin_lectura_reciente": True}, {"restantes": Decimal(0)}],
)
def test_proyeccion_conserva_los_bloqueos_de_la_ficha(cambios):
    assert proyectar(registros_354(), ficha(**cambios)) == FALLO


@pytest.mark.parametrize(
    "registros",
    [
        registros_354() + [{"estado": "pendiente"}],
        registros_354() + [registro(3, 1410071)],
        [registro(14, 10000), registro(7, 9900), registro(0, 12000)],
        [registro(4, 10000), registro(2, 11000), registro(0, 12000)],
    ],
)
def test_proyeccion_no_estima_con_series_invalidas(registros):
    assert proyectar(registros, ficha()) == FALLO


async def test_proyeccion_de_ficha_y_grafico_coinciden(monkeypatch):
    corte = date(2026, 11, 20)
    monkeypatch.setattr("app.modules.control_mantenciones.services.queries.hoy", lambda: corte)
    servicio = QueryService(AsyncMock())
    servicio.ficha = AsyncMock(return_value=ficha())
    servicio.serie_periodo = AsyncMock(return_value=registros_354())
    servicio.punto_anterior = AsyncMock(return_value=None)

    estimacion = await servicio.proyeccion(17)
    filtros = servicio.serie_periodo.await_args.args[0]
    assert filtros.desde == date(2026, 8, 22)
    assert filtros.hasta == corte
    grafico = await servicio.grafico(17)
    assert grafico["proyeccion"] == estimacion
    assert estimacion["fecha"] == date(2026, 12, 14)
    assert grafico["proxima_mantencion"] == Decimal(1430091)
