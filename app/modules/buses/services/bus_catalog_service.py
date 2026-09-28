import logging
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.buses.dtos.bus_query_dto import BusAutocompleteDTO, BusSimpleDTO
from app.modules.buses.dtos.bus_lifecycle_dto import BusResponseDTO
from app.modules.buses.models.bus import Bus
from app.modules.buses.repository.bus_repository import BusRepository, bus_repository

logger = logging.getLogger(__name__)


def es_bus_operativo_taller(n_bus: Optional[str]) -> bool:
    """Verifica si el número de bus es válido para operaciones de taller."""
    if not n_bus:
        return False
    return bool(str(n_bus).strip())


def _filtrar_flota_operativa(buses: List[Bus]) -> List[Bus]:
    """Filtra una colección de buses conservando los que poseen número de máquina."""
    return [b for b in buses if es_bus_operativo_taller(b.n_bus)]


def _mapear_y_deduplicar_buses_simples(buses: List[Bus]) -> List[BusSimpleDTO]:
    """Transforma entidades Bus a BusSimpleDTO garantizando unicidad por ID."""
    dtos: List[BusSimpleDTO] = []
    vistos: set[int] = set()
    for b in buses:
        if not b.n_bus:
            continue
        s_nb = str(b.n_bus).strip()
        if not s_nb or b.id in vistos:
            continue
        vistos.add(b.id)
        dtos.append(
            BusSimpleDTO(
                id=b.id,
                n_bus=s_nb,
                patente=b.patente,
                en_taller=bool(b.en_taller),
            )
        )
    return dtos


def _ordenar_buses_por_numero(dtos: List[BusSimpleDTO]) -> List[BusSimpleDTO]:
    """Ordena buses numéricamente según n_bus (con fallback lexicográfico seguro)."""
    def sort_key(dto: BusSimpleDTO) -> tuple[int, Any]:
        try:
            return (0, int(dto.n_bus))
        except ValueError:
            return (1, dto.n_bus)

    return sorted(dtos, key=sort_key)


class BusCatalogService:
    """Servicio especializado en consultas, catálogos, autocompletados y búsqueda de buses."""

    def __init__(self, repository: Optional[BusRepository] = None) -> None:
        self.repo = repository or bus_repository

    async def buscar_sugerencias_buses(
        self,
        db: AsyncSession,
        query: Optional[str] = None,
        solo_flota_taller: bool = True,
        limit: Optional[int] = None,
    ) -> List[BusSimpleDTO]:
        """Coordina la búsqueda de sugerencias de buses (id, n_bus, patente, en_taller)."""
        prefix = (query or "").strip()
        logger.debug(
            "[BUSES-CATALOG] Buscando sugerencias de buses | query='%s', solo_flota_taller=%s",
            prefix,
            solo_flota_taller,
        )
        buses = await self.repo.buscar_por_prefijo(
            db,
            prefix=prefix,
            solo_activos=True,
            solo_flota_taller=solo_flota_taller,
            limit=limit,
        )

        dtos = _mapear_y_deduplicar_buses_simples(buses)
        return _ordenar_buses_por_numero(dtos)

    async def get_bus_by_id(self, db: AsyncSession, bus_id: int) -> BusResponseDTO:
        """Recupera la ficha completa de un bus por su ID numérico."""
        bus = await self.repo.get_by_id(db, bus_id)
        if not bus:
            logger.warning("[BUSES-CATALOG] Bus no encontrado por ID | id=%s", bus_id)
            raise NotFoundException(f"Bus con ID {bus_id} no encontrado")
        return BusResponseDTO.model_validate(bus)

    async def get_bus_by_n_bus(self, db: AsyncSession, n_bus: str) -> BusResponseDTO:
        """Recupera la ficha de un bus a partir de su número de máquina asignado."""
        bus = await self.repo.get_by_n_bus(db, n_bus)
        if not bus:
            logger.warning("[BUSES-CATALOG] Bus no encontrado por n_bus | n_bus='%s'", n_bus)
            raise NotFoundException(f"Bus con número '{n_bus}' no encontrado")
        return BusResponseDTO.model_validate(bus)

    async def listar_buses(
        self,
        db: AsyncSession,
        solo_activos: bool = True,
        solo_flota_taller: bool = True,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> List[BusAutocompleteDTO]:
        """Coordina el listado de buses para catálogo y componentes de autocompletado."""
        logger.debug(
            "[BUSES-CATALOG] Listando catálogo de buses | solo_activos=%s, solo_flota_taller=%s, skip=%s, limit=%s",
            solo_activos,
            solo_flota_taller,
            skip,
            limit,
        )
        buses = await self.repo.get_all(
            db,
            solo_activos=solo_activos,
            solo_flota_taller=solo_flota_taller,
            skip=skip,
            limit=limit,
        )
        return [BusAutocompleteDTO.model_validate(b) for b in buses]

    async def count_buses(
        self,
        db: AsyncSession,
        solo_activos: bool = True,
        solo_flota_taller: bool = False,
    ) -> int:
        """Retorna el conteo total de buses en el sistema según filtros de búsqueda."""
        return await self.repo.count_buses(
            db, solo_activos=solo_activos, solo_flota_taller=solo_flota_taller
        )


bus_catalog_service = BusCatalogService()
