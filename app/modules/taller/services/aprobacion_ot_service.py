"""Conversión irreversible de solicitud a OT dentro de la transacción llamante."""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.realtime.events import RealtimeEvent, publish_event_soon
from app.modules.taller.dtos.solicitud_dto import SolicitudDTO
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.repository.taller_repository import taller_repository
from app.modules.taller.services.estadias_helper import attach_comentario_safe
from app.modules.taller.services.mappers import orm_to_solicitud_dto

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AprobacionOT:
    actor_id: int
    actor_nombre: Optional[str]
    motivo: str
    fecha_evento: Optional[datetime] = None


async def aprobar_como_ot(db: AsyncSession, solicitud: TallerSolicitud, aprobacion: AprobacionOT) -> bool:
    if solicitud.es_ot:
        return False
    now = aprobacion.fecha_evento or datetime.now(timezone.utc)
    solicitud.es_ot = True
    solicitud.fecha_actualizacion = now
    comentario = TallerSolicitudComentario(
        solicitud_id=solicitud.id, usuario_id=aprobacion.actor_id, tipo="SISTEMA",
        comentario=f"Solicitud aprobada como OT. {aprobacion.motivo}", fecha_registro=now,
    )
    db.add(comentario)
    attach_comentario_safe(solicitud, comentario, aprobacion.actor_nombre)
    logger.info("Solicitud aprobada como OT | id=%s | actor_id=%s | motivo=%s",
                solicitud.id, aprobacion.actor_id, aprobacion.motivo)
    return True


async def aprobar_solicitud(db: AsyncSession, solicitud_id: int, aprobacion: AprobacionOT) -> SolicitudDTO:
    await taller_repository.lock_solicitud_estado(db, solicitud_id)
    solicitud = await taller_repository.get_solicitud_operacional(db, solicitud_id)
    if solicitud is None:
        raise NotFoundException("Solicitud de taller no encontrada")
    cambio = await aprobar_como_ot(db, solicitud, aprobacion)
    await taller_repository.flush(db)
    resultado = orm_to_solicitud_dto(solicitud)
    await db.commit()
    if cambio:
        publish_event_soon(RealtimeEvent(
            resource_type="work_order", resource_id=solicitud.id,
            action="approved", actor_id=aprobacion.actor_id, version=solicitud.fecha_actualizacion,
        ))
    return resultado
