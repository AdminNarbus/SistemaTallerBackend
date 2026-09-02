import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.buses.dtos.bus_dto import BusAutocompleteDTO, BusResponseDTO
from app.modules.buses.repository.bus_repository import bus_repository

logger = logging.getLogger(__name__)


class BusService:
    """Capa de servicio de negocio para el catálogo de Buses."""

    async def buscar_sugerencias_buses(
        self, db: AsyncSession, query: Optional[str] = None
    ) -> List[str]:
        """
        Devuelve la lista de números de bus (n_bus) que coinciden con el prefijo ingresado.
        Si query es None o vacío, retorna todos los n_bus activos ordenados.
        """
        prefix = (query or "").strip()
        logger.debug("[BUSES] Buscando sugerencias de buses | query='%s'", prefix)
        return await bus_repository.buscar_n_buses_por_prefijo(db, prefix=prefix)

    async def get_bus_by_id(self, db: AsyncSession, bus_id: int) -> BusResponseDTO:
        bus = await bus_repository.get_by_id(db, bus_id)
        if not bus:
            logger.warning("[BUSES] Bus no encontrado por ID | id=%s", bus_id)
            raise NotFoundException(f"Bus con ID {bus_id} no encontrado")
        return BusResponseDTO.model_validate(bus)

    async def get_bus_by_n_bus(self, db: AsyncSession, n_bus: str) -> BusResponseDTO:
        bus = await bus_repository.get_by_n_bus(db, n_bus)
        if not bus:
            logger.warning("[BUSES] Bus no encontrado por n_bus | n_bus='%s'", n_bus)
            raise NotFoundException(f"Bus con número '{n_bus}' no encontrado")
        return BusResponseDTO.model_validate(bus)

    async def listar_buses(
        self, db: AsyncSession, solo_activos: bool = True
    ) -> List[BusAutocompleteDTO]:
        buses = await bus_repository.get_all(db, solo_activos=solo_activos)
        return [BusAutocompleteDTO.model_validate(b) for b in buses]


bus_service = BusService()
