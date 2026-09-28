from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.taller.constants import EstadoSolicitud


class ComentarioCreateDTO(BaseModel):
    """Payload para añadir un comentario general o técnico a la bitácora."""
    comentario: str
    tipo: Optional[str] = "GENERAL"


class SolicitudComentarioDTO(BaseModel):
    """Entrada inmutable del historial de bitácora de la orden de trabajo."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    usuario_id: int
    usuario_nombre: Optional[str] = None
    tipo: str
    comentario: str
    fecha_registro: datetime


class ComentarioAddedDTO(BaseModel):
    """Respuesta ultraligera tras agregar comentario (0 RTTs adicionales)."""
    comentario_id: int
    solicitud_id: int
    usuario_id: int
    usuario_nombre: Optional[str] = None
    tipo: str
    comentario: str
    fecha_registro: datetime


class CambiarEstadoSolicitudDTO(BaseModel):
    """Payload para cambio de estado administrativo de una OT por supervisión."""
    estado: EstadoSolicitud = Field(
        ...,
        description="Nuevo estado canónico de la solicitud (PENDIENTE, EN_REPARACION, LIBERADO, FINALIZADO)",
    )
    comentario: Optional[str] = Field(
        None,
        max_length=1000,
        description="Justificación u observación opcional del cambio de estado por la supervisora",
    )
    liberar_bus_taller: Optional[bool] = Field(
        None,
        description="Opcional: Si se pasa a LIBERADO o FINALIZADO, indica si se libera el bus de taller (en_taller = False). Por defecto True.",
    )

    @field_validator("estado", mode="before")
    @classmethod
    def normalizar_estado(cls, v: Any) -> Any:
        if isinstance(v, str):
            val = v.upper().strip()
            if val == "REPORTADO":
                return EstadoSolicitud.PENDIENTE
            return val
        if v == EstadoSolicitud.REPORTADO:
            return EstadoSolicitud.PENDIENTE
        return v


class FinalizarSolicitudDTO(BaseModel):
    """Payload para finalizar una OT y verificar checklist y averías resueltas."""
    comentario_cierre: Optional[str] = None
    motivo_incompleto_checklist: Optional[str] = None
    motivo_cierre_parcial: Optional[str] = None
    liberar_bus_taller: bool = True


class LiberarSolicitudDTO(FinalizarSolicitudDTO):
    """Payload para cierre y liberación de la unidad hacia ruta."""
    pass
