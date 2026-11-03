import logging

from app.core.exceptions import BusinessRuleException
from app.modules.dashboard.dtos.buses_dto import (
    BusOptionDTO,
    MechanicOptionDTO,
    OrderOptionDTO,
    PeriodOptionDTO,
)
from app.modules.dashboard.dtos.common import PageDTO
from app.modules.dashboard.dtos.indicadores_dto import IndicatorsDTO
from app.modules.dashboard.dtos.series_dto import (
    AgeSeriesDTO,
    BusSeriesDTO,
    ExternalWorkshopDTO,
    MechanicSeriesDTO,
    TrendSeriesDTO,
    WorkshopSeriesDTO,
)
from app.modules.dashboard.dtos.solicitudes_dto import OrderDTO
from app.modules.dashboard.services.common import ReadService

logger = logging.getLogger(__name__)
SERIES_MODELS = {
    "tendencia": TrendSeriesDTO,
    "antiguedad": AgeSeriesDTO,
    "mecanicos": MechanicSeriesDTO,
    "buses-fallas": BusSeriesDTO,
    "buses-visitas": BusSeriesDTO,
    "talleres": WorkshopSeriesDTO,
}
OPTION_MODELS = {
    "buses": BusOptionDTO,
    "solicitudes": OrderOptionDTO,
    "mecanicos": MechanicOptionDTO,
    "periodos": PeriodOptionDTO,
}


class DashboardService(ReadService):
    async def indicators(self, filters):
        historical = await self.repository.historical_states(filters)
        current = await self.repository.current_states(filters)
        durations = self._durations(await self.repository.durations(filters))
        monthly = await self.repository.monthly(filters)
        data = IndicatorsDTO(
            estados={**historical, **current}, tiempos=durations, mensuales=monthly
        )
        logger.debug("[DASHBOARD] Indicadores consultados bajo demanda")
        return await self.envelope(data)

    @staticmethod
    def _durations(values):
        return {
            name: {
                "promedio_horas": values[f"{name}_promedio"],
                "mediana_horas": values[f"{name}_mediana"],
                "validos": values[f"{name}_validos"],
                "sin_datos": values[f"{name}_sin_datos"],
                "invalidos": values[f"{name}_invalidos"],
            }
            for name in ("respuesta", "reparacion", "completo")
        }

    async def series(self, request):
        name, filters = request
        page = await self.repository.series(name, filters)
        values = {**page.as_dict(), "serie": name, "periodos_aplicados": filters.periodos}
        if name == "antiguedad":
            values["fecha_corte_calculo"] = await self.repository.age_cutoff()
        if name == "talleres":
            values.update(await self.repository.workshop_coverage(filters))
        return await self.envelope(SERIES_MODELS[name](**values))

    async def orders(self, filters):
        page = await self.repository.orders(filters)
        return await self.envelope(PageDTO[OrderDTO](**page.as_dict()))

    async def external_workshops(self, filters):
        page = await self.repository.external_workshops(filters)
        return await self.envelope(PageDTO[ExternalWorkshopDTO](**page.as_dict()))


class FilterService(ReadService):
    async def options(self, request):
        resource, filters = request
        self._validate_context(request)
        page = await self.repository.options(request)
        return await self.envelope(PageDTO[OPTION_MODELS[resource]](**page.as_dict()))

    @staticmethod
    def _validate_context(request):
        resource, filters = request
        contexts = {
            "buses": {None, "general", "maquina", "tabla"},
            "solicitudes": {None, "general", "tabla"},
            "mecanicos": {None, "general"},
            "periodos": {None, "ot", "cronologia"},
        }
        if filters.contexto not in contexts[resource]:
            raise BusinessRuleException("Contexto incompatible con el recurso solicitado.")
