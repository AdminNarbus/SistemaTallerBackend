"""Aprobación independiente de las fallas agregadas a una orden."""
from datetime import datetime, timezone
import logging

from app.core.exceptions import BusinessRuleException, NotFoundException, PermissionException
from app.core.realtime.events import RealtimeEvent, publish_event_soon
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.repository.taller_repository import taller_repository
from app.modules.taller.services.mappers import orm_to_solicitud_dto

logger = logging.getLogger(__name__)


def exigir_falla_aprobada(detalle):
    if detalle.estado_revision != "APROBADA":
        raise BusinessRuleException("La falla debe estar aprobada antes de intervenirla; asígnela o solicite el visto bueno de supervisión")


def aprobar_detalle(detalle, aprobacion):
    if detalle.estado_revision == "APROBADA":
        return
    detalle.estado_revision = "APROBADA"
    detalle.revisado_por_id = aprobacion.actor_id
    detalle.fecha_revision = aprobacion.fecha_evento or datetime.now(timezone.utc)


async def puede_aprobar_reporte(db, contexto):
    repo, solicitud_id, actor_id, rol = contexto
    if rol in ("SUPERVISOR", "ADMIN"):
        return True
    if rol != "MECANICO" or solicitud_id is None:
        return False
    asignaciones = await repo.get_asignaciones_activas(db, solicitud_id=solicitud_id)
    return any(a.mecanico_id == actor_id for a in asignaciones)


async def aprobar_falla(db, contexto):
    solicitud_id, detalle_id, actor_id, actor_nombre = contexto
    actor = await taller_repository.get_usuario_by_id(db, actor_id)
    rol = getattr(getattr(actor, "rol_rel", None), "nombre", "")
    if not actor or not actor.is_active or rol not in ("SUPERVISOR", "ADMIN"):
        raise PermissionException("Solo supervisión puede aprobar una falla")
    await taller_repository.lock_solicitud_estado(db, solicitud_id)
    solicitud = await taller_repository.get_solicitud_con_detalles(db, solicitud_id)
    if solicitud is None:
        raise NotFoundException("Solicitud de taller no encontrada")
    if not solicitud.es_ot or solicitud.estado == "FINALIZADO":
        raise BusinessRuleException("La OT debe estar aprobada y abierta")
    detalle = next((d for d in solicitud.detalles if d.id == detalle_id), None)
    if detalle is None:
        raise NotFoundException("Falla no encontrada en esta OT")
    if detalle.estado_revision == "APROBADA":
        return orm_to_solicitud_dto(solicitud)
    await _registrar_aprobacion(db, (solicitud, detalle, actor_id, actor_nombre))
    resultado = orm_to_solicitud_dto(solicitud)
    await db.commit()
    publish_event_soon(RealtimeEvent(resource_type="work_order", resource_id=solicitud_id,
                                   action="updated", actor_id=actor_id, version=solicitud.fecha_actualizacion))
    return resultado


async def _registrar_aprobacion(db, contexto):
    from app.modules.taller.services.aprobacion_ot_service import AprobacionOT
    from app.modules.taller.services.estadias_helper import attach_comentario_safe
    solicitud, detalle, actor_id, actor_nombre = contexto
    now = datetime.now(timezone.utc)
    aprobar_detalle(detalle, AprobacionOT(actor_id, actor_nombre, "Revisión de falla", now))
    solicitud.fecha_actualizacion = now
    comentario = TallerSolicitudComentario(solicitud_id=solicitud.id, usuario_id=actor_id,
        tipo="SUPERVISION", comentario=f"Falla #{detalle.id} aprobada por supervisión.", fecha_registro=now)
    db.add(comentario)
    attach_comentario_safe(solicitud, comentario, actor_nombre)
    await taller_repository.flush(db)
    logger.info("Falla aprobada | solicitud_id=%s | detalle_id=%s | actor_id=%s", solicitud.id, detalle.id, actor_id)
