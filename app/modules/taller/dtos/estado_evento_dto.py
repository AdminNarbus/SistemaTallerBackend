from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.modules.taller.constants import EstadoSolicitud


class EstadoEventoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    tipo_evento: Literal["CREACION", "CAMBIO_ESTADO", "CIERRE_HISTORICO"]
    estado_anterior: Optional[EstadoSolicitud]
    estado_nuevo: Optional[EstadoSolicitud]
    usuario_actor_id: Optional[int]
    actor_nombre_snapshot: str
    fecha_evento: datetime
    motivo: Optional[str]
    comentario_id: Optional[int]
    origen: Literal["OPERACION", "BITACORA"]

    @field_validator("fecha_evento")
    @classmethod
    def fecha_utc(cls, value: datetime) -> datetime:
        # SQLite de pruebas pierde tzinfo; PostgreSQL devuelve timestamptz.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
