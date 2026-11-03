from app.core.exceptions import NotFoundException
from app.modules.dashboard.dtos.common import PageDTO
from app.modules.dashboard.dtos.cronologia_dto import (
    HistoricalFaultDTO,
    MilestoneDTO,
    TimelineSummaryDTO,
)
from app.modules.dashboard.dtos.filtros_dto import GeneralQueryDTO
from app.modules.dashboard.services.common import ReadService, require_bus


class CronologiaService(ReadService):
    def __init__(self, repository, bus_repository):
        super().__init__(repository)
        self.bus_repository = bus_repository

    async def timeline(self, request):
        await require_bus(self.bus_repository, request[0])
        page = await self.repository.timeline(request)
        return await self.envelope(PageDTO[MilestoneDTO](**page.as_dict()))

    async def details(self, request):
        await require_bus(self.bus_repository, request[0])
        await self._validate_milestone(request)
        page = await self.repository.details(request)
        event_ids = {
            row["evento_falla_id"] for row in page.items if row["evento_falla_id"] is not None
        }
        authors = self._authors(await self.repository.authors(event_ids))
        items = [self._detail(row, authors) for row in page.items]
        return await self.envelope(
            PageDTO[HistoricalFaultDTO](
                items=items, total=page.total, skip=page.skip, limit=page.limit
            )
        )

    async def _validate_milestone(self, request):
        if request[1].hito_id and not await self.repository.has_milestone(request):
            raise NotFoundException("Hito no encontrado para el bus y los filtros solicitados.")

    @staticmethod
    def _authors(rows):
        result = {}
        for row in rows:
            result.setdefault(row["evento_id"], []).append(row["nombre"])
        return result

    @staticmethod
    def _detail(row, authors):
        values = {
            key: value for key, value in row.items() if key not in {"evento_falla_id", "sort_id"}
        }
        values["mecanicos_nombres"] = (
            authors.get(row["evento_falla_id"], [])
            if row["estado_falla"] in {"RESUELTA", "INCOMPLETA"}
            else []
        )
        return HistoricalFaultDTO(**values)

    async def summary(self, request):
        bus_id, _ = request
        bus = await require_bus(self.bus_repository, bus_id)
        latest = await self.bus_repository.latest((bus_id, GeneralQueryDTO()))
        counts = await self.repository.summary(request)
        data = TimelineSummaryDTO(
            bus=bus, estado_actual=latest["estado"] if latest else None, **counts
        )
        return await self.envelope(data)
