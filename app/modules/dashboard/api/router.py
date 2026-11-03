from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from app.api.deps import require_supervisor_or_admin
from app.modules.dashboard.api.dependencies import (
    bus_service,
    dashboard_service,
    filter_service,
    no_store,
    paged_response,
    timeline_service,
)
from app.modules.dashboard.dtos.buses_dto import (
    BusOptionDTO,
    BusSummaryDTO,
    FaultGroupDTO,
    FaultOrderDTO,
    MechanicOptionDTO,
    OrderOptionDTO,
    PeriodOptionDTO,
)
from app.modules.dashboard.dtos.common import EnvelopeDTO, PageDTO
from app.modules.dashboard.dtos.cronologia_dto import (
    HistoricalFaultDTO,
    MilestoneDTO,
    TimelineSummaryDTO,
)
from app.modules.dashboard.dtos.filtros_dto import (
    BusQueryDTO,
    FaultOrdersQueryDTO,
    FaultQueryDTO,
    FilterQueryDTO,
    GeneralQueryDTO,
    ResourceName,
    SeriesName,
    SeriesQueryDTO,
    SolicitudesQueryDTO,
    TimelineDetailsQueryDTO,
    TimelineQueryDTO,
)
from app.modules.dashboard.dtos.indicadores_dto import IndicatorsDTO
from app.modules.dashboard.dtos.series_dto import ExternalWorkshopDTO, SeriesDTO
from app.modules.dashboard.dtos.solicitudes_dto import OrderDTO
from app.modules.dashboard.services.bus_dashboard_service import BusDashboardService
from app.modules.dashboard.services.cronologia_service import CronologiaService
from app.modules.dashboard.services.dashboard_service import DashboardService, FilterService

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(require_supervisor_or_admin), Depends(no_store)],
)
DashboardDep = Annotated[DashboardService, Depends(dashboard_service)]
BusDep = Annotated[BusDashboardService, Depends(bus_service)]
TimelineDep = Annotated[CronologiaService, Depends(timeline_service)]
FilterDep = Annotated[FilterService, Depends(filter_service)]
BusId = Annotated[int, Path(gt=0)]
FilterPage = (
    PageDTO[BusOptionDTO]
    | PageDTO[OrderOptionDTO]
    | PageDTO[MechanicOptionDTO]
    | PageDTO[PeriodOptionDTO]
)


@router.get("/indicadores", response_model=EnvelopeDTO[IndicatorsDTO])
async def indicators(filters: Annotated[GeneralQueryDTO, Query()], service: DashboardDep):
    return await service.indicators(filters)


@router.get("/series/{serie}", response_model=EnvelopeDTO[SeriesDTO])
async def series(
    serie: SeriesName,
    filters: Annotated[SeriesQueryDTO, Query()],
    service: DashboardDep,
    response: Response,
):
    return paged_response(response, await service.series((serie, filters)))


@router.get("/talleres/externos", response_model=EnvelopeDTO[PageDTO[ExternalWorkshopDTO]])
async def external_workshops(
    filters: Annotated[SeriesQueryDTO, Query()], service: DashboardDep, response: Response
):
    return paged_response(response, await service.external_workshops(filters))


@router.get("/solicitudes", response_model=EnvelopeDTO[PageDTO[OrderDTO]])
async def orders(
    filters: Annotated[SolicitudesQueryDTO, Query()], service: DashboardDep, response: Response
):
    return paged_response(response, await service.orders(filters))


@router.get("/buses/{bus_id}/resumen", response_model=EnvelopeDTO[BusSummaryDTO])
async def bus_summary(bus_id: BusId, filters: Annotated[BusQueryDTO, Query()], service: BusDep):
    return await service.summary((bus_id, filters))


@router.get("/buses/{bus_id}/fallas", response_model=EnvelopeDTO[PageDTO[FaultGroupDTO]])
async def fault_groups(
    bus_id: BusId, filters: Annotated[FaultQueryDTO, Query()], service: BusDep, response: Response
):
    return paged_response(response, await service.fault_groups((bus_id, filters)))


@router.get(
    "/buses/{bus_id}/fallas/solicitudes", response_model=EnvelopeDTO[PageDTO[FaultOrderDTO]]
)
async def fault_orders(
    bus_id: BusId,
    filters: Annotated[FaultOrdersQueryDTO, Query()],
    service: BusDep,
    response: Response,
):
    return paged_response(response, await service.fault_orders((bus_id, filters)))


@router.get("/buses/{bus_id}/cronologia", response_model=EnvelopeDTO[PageDTO[MilestoneDTO]])
async def timeline(
    bus_id: BusId,
    filters: Annotated[TimelineQueryDTO, Query()],
    service: TimelineDep,
    response: Response,
):
    return paged_response(response, await service.timeline((bus_id, filters)))


@router.get(
    "/buses/{bus_id}/cronologia/detalles", response_model=EnvelopeDTO[PageDTO[HistoricalFaultDTO]]
)
async def timeline_details(
    bus_id: BusId,
    filters: Annotated[TimelineDetailsQueryDTO, Query()],
    service: TimelineDep,
    response: Response,
):
    return paged_response(response, await service.details((bus_id, filters)))


@router.get("/buses/{bus_id}/cronologia/resumen", response_model=EnvelopeDTO[TimelineSummaryDTO])
async def timeline_summary(
    bus_id: BusId, filters: Annotated[TimelineQueryDTO, Query()], service: TimelineDep
):
    return await service.summary((bus_id, filters))


@router.get("/filtros/{recurso}", response_model=EnvelopeDTO[FilterPage])
async def filter_options(
    recurso: ResourceName,
    filters: Annotated[FilterQueryDTO, Query()],
    service: FilterDep,
    response: Response,
):
    return paged_response(response, await service.options((recurso, filters)))
