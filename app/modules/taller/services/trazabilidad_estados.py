"""Registro de estados dentro de la transacción de la operación."""
from datetime import datetime
from dataclasses import dataclass
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.taller.models.taller_solicitud_estado_evento import TallerSolicitudEstadoEvento
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class RegistroEstadoOT:
    solicitud_id: int
    estado_anterior: Optional[str]
    estado_nuevo: str
    actor_id: Optional[int]
    actor_nombre: Optional[str]
    fecha_evento: datetime
    comentario: Optional[TallerSolicitudComentario] = None
    motivo: Optional[str] = None
    tipo_evento: str = "CAMBIO_ESTADO"


async def registrar_evento_estado(db: AsyncSession, registro: RegistroEstadoOT) -> Optional[TallerSolicitudEstadoEvento]:
    """Agrega el evento sin confirmar la transacción del caso de uso."""
    if registro.tipo_evento == "CAMBIO_ESTADO" and registro.estado_anterior == registro.estado_nuevo:
        return None
    comentario = registro.comentario
    if comentario is not None and comentario.id is None:
        # Persistir el comentario primero evita depender del orden de inserts ORM.
        await db.flush()
    evento = TallerSolicitudEstadoEvento(
        solicitud_id=registro.solicitud_id, tipo_evento=registro.tipo_evento,
        estado_anterior=registro.estado_anterior, estado_nuevo=registro.estado_nuevo,
        usuario_actor_id=registro.actor_id, actor_nombre_snapshot=((registro.actor_nombre or "No registrado").strip() or "No registrado")[:200],
        fecha_evento=registro.fecha_evento, motivo=registro.motivo,
        comentario_id=comentario.id if comentario is not None else None,
        origen="OPERACION",
    )
    db.add(evento)
    logger.debug("Evento de estado preparado | solicitud_id=%s | anterior=%s | nuevo=%s | actor_id=%s", registro.solicitud_id, registro.estado_anterior, registro.estado_nuevo, registro.actor_id)
    return evento
