from datetime import datetime, timezone
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import BusinessRuleException, ConflictException, NotFoundException
from app.modules.buses.dtos.bus_lifecycle_dto import BusCreateDTO, BusDarDeBajaDTO, BusResponseDTO
from app.modules.buses.models.bus import Bus
from app.modules.buses.repository.bus_repository import BusRepository, bus_repository
from app.core.realtime.events import RealtimeEvent, publish_event_soon

logger = logging.getLogger(__name__)


class BusFleetService:
    """Servicio especializado en el ciclo de vida, altas, bajas auditadas y reactivación de flota."""

    def __init__(self, repository: Optional[BusRepository] = None) -> None:
        self.repo = repository or bus_repository

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
        if bus_existente:
            raise ConflictException(f"Ya existe un bus registrado con la patente '{dto.patente}'; reactive su ficha si está dado de baja")

        if dto.n_bus:
            bus_num = await self.repo.get_by_n_bus(db, dto.n_bus)
            if bus_num:
                raise ConflictException(f"Ya existe un bus registrado con el número de máquina '{dto.n_bus}'")

        now = datetime.now(timezone.utc)
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
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictException("El bus ya existe o sus datos incumplen las restricciones de la flota") from exc
        publish_event_soon(RealtimeEvent(
            resource_type="bus", resource_id=bus.id, action="created", actor_id=usuario_id
        ))

        logger.info(
            "[BUSES-FLEET] Bus creado exitosamente | id=%s, patente='%s', n_bus='%s', supervisor_id=%s",
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

        now = datetime.now(timezone.utc)
        bus.is_active = False
        bus.en_taller = False
        bus.fecha_baja = now
        bus.motivo_baja = dto.motivo
        bus.usuario_baja_id = usuario_id
        await db.commit()
        publish_event_soon(RealtimeEvent(
            resource_type="bus", resource_id=bus.id, action="deactivated", actor_id=usuario_id
        ))

        logger.info(
            "[BUSES-FLEET] Bus dado de baja | bus_id=%s, n_bus='%s', motivo='%s', supervisor_id=%s",
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
        publish_event_soon(RealtimeEvent(
            resource_type="bus", resource_id=bus.id, action="reactivated", actor_id=usuario_id
        ))

        logger.info(
            "[BUSES-FLEET] Bus reactivado exitosamente | bus_id=%s, n_bus='%s', supervisor_id=%s",
            bus.id,
            bus.n_bus,
            usuario_id,
        )
        return BusResponseDTO.model_validate(bus)


bus_fleet_service = BusFleetService()
