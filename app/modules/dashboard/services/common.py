from app.core.exceptions import NotFoundException
from app.modules.dashboard.dtos.common import EnvelopeDTO, MetadataDTO


class ReadService:
    def __init__(self, repository):
        self.repository = repository

    async def envelope(self, data):
        reference = await self.repository.reference()
        return EnvelopeDTO(metadata=MetadataDTO(fecha_referencia_datos=reference), data=data)


async def require_bus(repository, bus_id):
    bus = await repository.bus(bus_id)
    if bus is None:
        raise NotFoundException("Bus no encontrado.")
    return bus
