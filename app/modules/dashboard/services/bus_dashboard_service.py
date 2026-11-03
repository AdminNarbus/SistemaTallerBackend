from app.modules.dashboard.dtos.buses_dto import BusSummaryDTO, FaultGroupDTO, FaultOrderDTO
from app.modules.dashboard.dtos.common import PageDTO
from app.modules.dashboard.services.common import ReadService, require_bus


class BusDashboardService(ReadService):
    async def summary(self, request):
        bus_id, _ = request
        bus = await require_bus(self.repository, bus_id)
        latest = await self.repository.latest(request)
        counts = await self.repository.counts(request)
        recurrence = await self.repository.recurrences(request)
        visits = counts.pop("visitas")
        data = BusSummaryDTO(
            bus=bus,
            ultima_ot_id=latest["id"] if latest else None,
            estado=latest["estado"] if latest else None,
            visitas=visits,
            fallas=counts,
            reincidencias=recurrence,
        )
        return await self.envelope(data)

    async def fault_groups(self, request):
        await require_bus(self.repository, request[0])
        page = await self.repository.fault_groups(request)
        return await self.envelope(PageDTO[FaultGroupDTO](**page.as_dict()))

    async def fault_orders(self, request):
        await require_bus(self.repository, request[0])
        page = await self.repository.fault_orders(request)
        return await self.envelope(PageDTO[FaultOrderDTO](**page.as_dict()))
