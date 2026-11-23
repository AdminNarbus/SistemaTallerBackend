from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EstadoEnvio = Literal["PENDIENTE", "ENVIANDO", "ACEPTADO", "FALLIDO", "INCIERTO", "REINTENTABLE"]


class WhatsappNotificacionDTO(BaseModel):
    clave: str
    solicitud_id: int
    tipo: str
    severidad: str
    destinatario: str
    mensaje: str
    parametros: list[str]


class WhatsappResultadoDTO(BaseModel):
    estado: EstadoEnvio
    meta_message_id: str | None = None
    codigo_error: str | None = None
    proximo_intento: datetime | None = None


class WhatsappResumenDTO(BaseModel):
    alertas_activas: int = 0
    aceptados: int = 0
    omitidos: int = 0
    fallidos: int = 0
    inciertos: int = 0
    reintentos_pendientes: int = 0


class WhatsappEnvioDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    tipo: str
    severidad: str
    destinatario: str
    estado: EstadoEnvio
    intentos: int
    meta_message_id: str | None
    codigo_error: str | None
    proximo_intento: datetime | None
    created_at: datetime
    updated_at: datetime
