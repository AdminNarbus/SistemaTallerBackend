import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.buses.dtos.bus_dto import BusAutocompleteDTO, BusResponseDTO, BusSimpleDTO
from app.modules.buses.repository.bus_repository import bus_repository

logger = logging.getLogger(__name__)


class BusService:
    """Capa de servicio de negocio para el catálogo de Buses."""

    async def buscar_sugerencias_buses(
        self,
        db: AsyncSession,
        query: Optional[str] = None,
        solo_flota_taller: bool = True,
    ) -> List[BusSimpleDTO]:
        """
        Devuelve la lista de buses sugeridos (id, n_bus, patente, en_taller) que coinciden con el prefijo ingresado.
        Si query es None o vacío, retorna todos los buses activos ordenados numéricamente.
        Por defecto filtra vehículos que no pertenecen a la flota operativa de taller (200 <= n_bus < 900).
        """
        prefix = (query or "").strip()
        logger.debug(
            "[BUSES] Buscando sugerencias de buses | query='%s', solo_flota_taller=%s",
            prefix,
            solo_flota_taller,
        )
        return await bus_repository.buscar_n_buses_por_prefijo(
            db, prefix=prefix, solo_flota_taller=solo_flota_taller
        )

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
        self,
        db: AsyncSession,
        solo_activos: bool = True,
        solo_flota_taller: bool = True,
    ) -> List[BusAutocompleteDTO]:
        buses = await bus_repository.get_all(
            db, solo_activos=solo_activos, solo_flota_taller=solo_flota_taller
        )
        return [BusAutocompleteDTO.model_validate(b) for b in buses]

    async def actualizar_en_taller(
        self,
        db: AsyncSession,
        bus_id: int,
        en_taller: bool,
        motivo: Optional[str] = None,
    ) -> BusResponseDTO:
        """
        Actualiza el estado en_taller de un bus (movimiento suspendido en taller).
        """
        bus = await bus_repository.update_en_taller(db, bus_id=bus_id, en_taller=en_taller)
        if not bus:
            logger.warning("[BUSES] Bus no encontrado para actualizar en_taller | id=%s", bus_id)
            raise NotFoundException(f"Bus con ID {bus_id} no encontrado")

        await db.commit()
        await db.refresh(bus)

        logger.info(
            "[BUSES] Estado en_taller actualizado | bus_id=%s, en_taller=%s, motivo='%s'",
            bus_id,
            en_taller,
            motivo or "",
        )
        return BusResponseDTO.model_validate(bus)


bus_service = BusService()

