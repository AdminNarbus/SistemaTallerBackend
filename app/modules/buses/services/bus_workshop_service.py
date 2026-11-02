import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.buses.dtos.bus_lifecycle_dto import BusResponseDTO
from app.modules.buses.repository.bus_repository import BusRepository, bus_repository
from app.core.realtime.events import RealtimeEvent, publish_event_soon
from app.modules.taller.repository.taller_repository import TallerRepository, taller_repository
from app.modules.taller.services.estadias_helper import asegurar_ingreso_taller_y_estadia, cerrar_estadia_activa
from app.modules.taller.services.aprobacion_ot_service import AprobacionOT, aprobar_como_ot

logger = logging.getLogger(__name__)


class BusWorkshopService:
    """Servicio especializado en el estado físico y operacional del bus en taller."""

    def __init__(self, repository: Optional[BusRepository] = None, taller_repo: Optional[TallerRepository] = None) -> None:
        self.repo = repository or bus_repository
        self.taller_repo = taller_repo or taller_repository

    async def actualizar_en_taller(
        self,
        db: AsyncSession,
        bus_id: int,
        en_taller: bool,
        motivo: Optional[str] = None,
        actor_id: Optional[int] = None,
        actor_nombre: Optional[str] = None,
    ) -> BusResponseDTO:
        """
        Sincroniza el movimiento físico y la estadía de la OT activa en una transacción.
        """
        solicitud = await self.taller_repo.get_solicitud_activa_por_bus(db, bus_id, None)
        ot_aprobada = False
        if solicitud:
            now = datetime.now(timezone.utc)
            if en_taller:
                if not solicitud.es_ot and actor_id is not None:
                    ot_aprobada = await aprobar_como_ot(
                        db,
                        solicitud,
                        AprobacionOT(
                            actor_id=actor_id,
                            actor_nombre=actor_nombre,
                            motivo="Ingreso físico del bus a taller",
                            fecha_evento=now,
                        ),
                    )
                await asegurar_ingreso_taller_y_estadia(self.taller_repo, db, solicitud, now)
            else:
                await cerrar_estadia_activa(self.taller_repo, db, solicitud, now, motivo or "MOVIMIENTO_FISICO")
        bus = await self.repo.update_en_taller_directo(
            db, bus_id=bus_id, en_taller=en_taller
        )
        if not bus:
            logger.warning("[BUSES-WORKSHOP] Bus no encontrado para actualizar en_taller | id=%s", bus_id)
            raise NotFoundException(f"Bus con ID {bus_id} no encontrado")

        await db.commit()
        publish_event_soon(RealtimeEvent(
            resource_type="bus", resource_id=bus_id, action="workshop_status_changed"
        ))
        if ot_aprobada:
            publish_event_soon(RealtimeEvent(
                resource_type="work_order", resource_id=solicitud.id,
                action="approved", actor_id=actor_id, version=solicitud.fecha_actualizacion,
            ))

        logger.info(
            "[BUSES-WORKSHOP] Estado en_taller actualizado atómicamente | bus_id=%s, en_taller=%s, motivo='%s'",
            bus_id,
            en_taller,
            motivo or "",
        )
        return BusResponseDTO.model_validate(bus)


bus_workshop_service = BusWorkshopService()
