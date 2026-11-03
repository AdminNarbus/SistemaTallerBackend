from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.dashboard.dtos.filtros_dto import (
    BusQueryDTO,
    FilterQueryDTO,
    TimelineDetailsQueryDTO,
)
from app.modules.dashboard.repository.base import QueryPage
from app.modules.dashboard.services.bus_dashboard_service import BusDashboardService
from app.modules.dashboard.services.cronologia_service import CronologiaService
from app.modules.dashboard.services.dashboard_service import FilterService


async def test_summary_without_orders_does_not_infer_bus_availability():
    # Arrange: persistence is isolated; an existing bus has no orders.
    repository = SimpleNamespace(
        bus=AsyncMock(return_value={"id": 1, "n_bus": "1", "patente": "TEST"}),
        latest=AsyncMock(return_value=None),
        counts=AsyncMock(
            return_value={"visitas": 0, "pendientes": 0, "incompletas": 0, "resueltas": 0}
        ),
        recurrences=AsyncMock(return_value={"periodo": None, "cantidad": 0}),
        reference=AsyncMock(return_value=None),
    )
    service = BusDashboardService(repository)
    # Act.
    result = await service.summary((1, BusQueryDTO()))
    # Assert.
    assert result.data.estado is None
    assert result.data.ultima_ot_id is None
    assert result.metadata.fecha_referencia_datos is None


async def test_missing_bus_fails_before_analytics_queries():
    repository = SimpleNamespace(bus=AsyncMock(return_value=None), latest=AsyncMock())
    service = BusDashboardService(repository)
    with pytest.raises(NotFoundException):
        await service.summary((99, BusQueryDTO()))
    repository.latest.assert_not_awaited()


async def test_invalid_filter_context_fails_before_persistence():
    repository = SimpleNamespace(options=AsyncMock())
    service = FilterService(repository)
    with pytest.raises(BusinessRuleException):
        await service.options(("mecanicos", FilterQueryDTO(contexto="maquina")))
    repository.options.assert_not_awaited()


async def test_stage_authors_are_batched_and_hidden_for_pending_faults():
    shared = {
        "solicitud_id": 1,
        "hito_id": "evento:1",
        "tipo_evento": "CREACION",
        "fecha_evento": "2026-10-01T12:00:00Z",
        "estado_ot": "PENDIENTE",
        "creador_nombre": None,
        "descripcion": "Aire",
        "fecha_reporte": "2026-10-01T12:00:00Z",
        "reportante_nombre": None,
        "sort_id": 1,
        "evento_falla_id": 10,
    }
    rows = [
        {**shared, "detalle_id": 1, "estado_falla": "PENDIENTE"},
        {**shared, "detalle_id": 2, "estado_falla": "RESUELTA"},
    ]
    repository = SimpleNamespace(
        details=AsyncMock(return_value=QueryPage(rows, 2, 0, 20)),
        authors=AsyncMock(return_value=[{"evento_id": 10, "nombre": "Nombre histórico"}]),
        reference=AsyncMock(return_value=date(2026, 10, 1)),
    )
    service = CronologiaService(repository, SimpleNamespace(bus=AsyncMock(return_value={"id": 1})))
    result = await service.details((1, TimelineDetailsQueryDTO()))
    repository.authors.assert_awaited_once_with({10})
    assert result.data.items[0].mecanicos_nombres == []
    assert result.data.items[1].mecanicos_nombres == ["Nombre histórico"]
