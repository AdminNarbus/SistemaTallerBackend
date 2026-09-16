from datetime import datetime
import logging
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, ConflictException, NotFoundException
from app.modules.buses.dtos import (
    BusAutocompleteDTO,
    BusCreateDTO,
    BusDarDeBajaDTO,
    BusResponseDTO,
    BusSimpleDTO,
)
from app.modules.buses.models.bus import Bus
from app.modules.buses.repository.bus_repository import BusRepository, bus_repository

logger = logging.getLogger(__name__)


def es_bus_operativo_taller(n_bus: Optional[str]) -> bool:
    """
    Regla de Dominio: Verifica si el número de bus es válido para operaciones de taller.
    Se removió la restricción artificial 200 <= n_bus < 900 para permitir toda la flota real.
    """
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


class BusService:
    """Capa de servicio de negocio para el catálogo y operaciones sobre Buses."""

    def __init__(self, repository: Optional[BusRepository] = None) -> None:
        self.repo = repository or bus_repository

    async def buscar_sugerencias_buses(
        self,
        db: AsyncSession,
        query: Optional[str] = None,
        solo_flota_taller: bool = True,
        limit: Optional[int] = None,
    ) -> List[BusSimpleDTO]:
        """
        Coordina la búsqueda de sugerencias de buses (id, n_bus, patente, en_taller).
        Aplica filtro de flota operativa y ordenamiento numérico.
        """
        prefix = (query or "").strip()
        logger.debug(
            "[BUSES] Buscando sugerencias de buses | query='%s', solo_flota_taller=%s",
            prefix,
            solo_flota_taller,
        )
        buses = await self.repo.buscar_por_prefijo(
            db, prefix=prefix, solo_activos=True, limit=limit
        )

        if solo_flota_taller:
            buses = _filtrar_flota_operativa(buses)

        dtos = _mapear_y_deduplicar_buses_simples(buses)
        return _ordenar_buses_por_numero(dtos)

    async def get_bus_by_id(self, db: AsyncSession, bus_id: int) -> BusResponseDTO:
        """Recupera la ficha completa de un bus por su ID numérico."""
        bus = await self.repo.get_by_id(db, bus_id)
        if not bus:
            logger.warning("[BUSES] Bus no encontrado por ID | id=%s", bus_id)
            raise NotFoundException(f"Bus con ID {bus_id} no encontrado")
        return BusResponseDTO.model_validate(bus)

    async def get_bus_by_n_bus(self, db: AsyncSession, n_bus: str) -> BusResponseDTO:
        """Recupera la ficha de un bus a partir de su número de máquina asignado."""
        bus = await self.repo.get_by_n_bus(db, n_bus)
        if not bus:
            logger.warning("[BUSES] Bus no encontrado por n_bus | n_bus='%s'", n_bus)
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
        """
        Coordina el listado de buses para catálogo y componentes de autocompletado.
        """
        logger.debug(
            "[BUSES] Listando catálogo de buses | solo_activos=%s, solo_flota_taller=%s, skip=%s, limit=%s",
            solo_activos,
            solo_flota_taller,
            skip,
            limit,
        )
        buses = await self.repo.get_all(
            db, solo_activos=solo_activos, skip=skip, limit=limit
        )
        if solo_flota_taller:
            buses = _filtrar_flota_operativa(buses)

        return [BusAutocompleteDTO.model_validate(b) for b in buses]

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
            logger.warning("[BUSES] Bus no encontrado para actualizar en_taller | id=%s", bus_id)
            raise NotFoundException(f"Bus con ID {bus_id} no encontrado")

        await db.commit()

        logger.info(
            "[BUSES] Estado en_taller actualizado atómicamente | bus_id=%s, en_taller=%s, motivo='%s'",
            bus_id,
            en_taller,
            motivo or "",
        )
        return BusResponseDTO.model_validate(bus)

    async def create_bus(
        self,
        db: AsyncSession,
        dto: BusCreateDTO,
        usuario_id: Optional[int] = None,
    ) -> BusResponseDTO:
        """
        Crea un nuevo bus en la base de datos validando unicidad de patente y n_bus.
        Asigna fecha_creacion con timestamp exacto para trazabilidad.
        """
        bus_existente = await self.repo.get_by_patente(db, dto.patente)
        if bus_existente and bus_existente.is_active:
            raise ConflictException(f"Ya existe un bus activo registrado con la patente '{dto.patente}'")

        if dto.n_bus:
            bus_num = await self.repo.get_by_n_bus(db, dto.n_bus)
            if bus_num and bus_num.is_active:
                raise ConflictException(f"Ya existe un bus activo registrado con el número de máquina '{dto.n_bus}'")

        now = datetime.now()
        bus = Bus(
            patente=dto.patente,
            n_bus=dto.n_bus,
            marca=dto.marca,
            modelo=dto.modelo,
            n_motor=dto.n_motor,
            n_chasis=dto.n_chasis,
            n_carroceria=dto.n_carroceria,
            astos=dto.astos,
            anio=dto.anio,
            servicio=dto.servicio,
            tipo_bus=dto.tipo_bus,
            empresa_id=dto.empresa_id,
            clasificacion=dto.clasificacion,
            min=dto.min,
            max=dto.max,
            tipo=dto.tipo,
            max_litros=dto.max_litros,
            is_active=True,
            en_taller=dto.en_taller,
            fecha_creacion=now,
        )
        self.repo.add_bus(db, bus)
        await db.commit()

        logger.info(
            "[BUSES] Bus creado exitosamente | id=%s, patente='%s', n_bus='%s', supervisor_id=%s",
            bus.id,
            bus.patente,
            bus.n_bus,
            usuario_id,
        )
        return BusResponseDTO.model_validate(bus)

    async def dar_de_baja_bus(
        self,
        db: AsyncSession,
        bus_id: int,
        dto: BusDarDeBajaDTO,
        usuario_id: Optional[int] = None,
    ) -> BusResponseDTO:
        """
        Da de baja a un bus desactivándolo (soft-delete), liberándolo de taller y registrando
        la fecha de baja, el motivo y el supervisor responsable.
        Valida que no tenga OTs activas a menos que se fuerce explícitamente.
        """
        bus = await self.repo.get_by_id(db, bus_id)
        if not bus:
            raise NotFoundException(f"Bus con ID {bus_id} no encontrado")

        if not bus.is_active:
            raise BusinessRuleException(f"El bus '{bus.n_bus or bus.patente}' ya se encuentra dado de baja")

        if not dto.forzar:
            cant_ots = await self.repo.count_solicitudes_activas_por_bus(db, bus_id)
            if cant_ots > 0:
                raise BusinessRuleException(
                    f"No se puede dar de baja el bus '{bus.n_bus or bus.patente}' porque tiene {cant_ots} orden(es) de trabajo abierta(s) en taller. "
                    "Finalice o cierre las OTs primero, o envíe 'forzar=true'."
                )

        now = datetime.now()
        bus.is_active = False
        bus.en_taller = False
        bus.fecha_baja = now
        bus.motivo_baja = dto.motivo
        bus.usuario_baja_id = usuario_id
        await db.commit()

        logger.info(
            "[BUSES] Bus dado de baja | bus_id=%s, n_bus='%s', motivo='%s', supervisor_id=%s",
            bus.id,
            bus.n_bus,
            dto.motivo,
            usuario_id,
        )
        return BusResponseDTO.model_validate(bus)

    async def reactivar_bus(
        self,
        db: AsyncSession,
        bus_id: int,
        usuario_id: Optional[int] = None,
    ) -> BusResponseDTO:
        """
        Reactiva un bus previamente dado de baja, limpiando los campos de baja para restituir su operatividad.
        """
        bus = await self.repo.get_by_id(db, bus_id)
        if not bus:
            raise NotFoundException(f"Bus con ID {bus_id} no encontrado")

        if bus.is_active:
            raise BusinessRuleException(f"El bus '{bus.n_bus or bus.patente}' ya se encuentra activo")

        bus.is_active = True
        bus.fecha_baja = None
        bus.motivo_baja = None
        bus.usuario_baja_id = None
        await db.commit()

        logger.info(
            "[BUSES] Bus reactivado exitosamente | bus_id=%s, n_bus='%s', supervisor_id=%s",
            bus.id,
            bus.n_bus,
            usuario_id,
        )
        return BusResponseDTO.model_validate(bus)


bus_service = BusService()

