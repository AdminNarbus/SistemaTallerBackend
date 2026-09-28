import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.buses.dtos.bus_lifecycle_dto import BusResponseDTO
from app.modules.buses.repository.bus_repository import BusRepository, bus_repository

logger = logging.getLogger(__name__)


class BusWorkshopService:
    """Servicio especializado en el estado físico y operacional del bus en taller."""

    def __init__(self, repository: Optional[BusRepository] = None) -> None:
        self.repo = repository or bus_repository

    async def actualizar_en_taller(
        self,
        db: AsyncSession,
        bus_id: int,
        en_taller: bool,
        motivo: Optional[str] = None,
    ) -> BusResponseDTO:
        """
        Actualiza el estado en_taller de un bus (movimiento físico a taller) en 1 solo viaje de red atómico.
        """
        bus = await self.repo.update_en_taller_directo(
            db, bus_id=bus_id, en_taller=en_taller
        )
        if not bus:
            logger.warning("[BUSES-WORKSHOP] Bus no encontrado para actualizar en_taller | id=%s", bus_id)
            raise NotFoundException(f"Bus con ID {bus_id} no encontrado")

        await db.commit()

        logger.info(
            "[BUSES-WORKSHOP] Estado en_taller actualizado atómicamente | bus_id=%s, en_taller=%s, motivo='%s'",
            bus_id,
            en_taller,
            motivo or "",
        )
        return BusResponseDTO.model_validate(bus)


bus_workshop_service = BusWorkshopService()
