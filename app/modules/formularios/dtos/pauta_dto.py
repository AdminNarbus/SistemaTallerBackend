from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, field_validator
from app.modules.taller.constants import EstadoItemPauta


class PautaTallerItemDTO(BaseModel):
    """Ítem del catálogo maestro de la pauta preventiva (10 ítems estándar)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria: str
    item: str
    orden: int
    is_active: bool


class PautaRespuestaCreateDTO(BaseModel):
    """Entrada individual para registrar el chequeo de un ítem de la pauta preventiva."""
    item_id: int
    estado: EstadoItemPauta
    observacion: Optional[str] = None

    @field_validator("estado", mode="before")
    @classmethod
    def normalizar_estado(cls, value: str) -> str:
        return "OK" if value == "BUENO" else value


class PautaRespuestaDTO(BaseModel):
    """Detalle de una respuesta guardada de pauta preventiva con trazabilidad del mecánico."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    item_id: int
    item_categoria: Optional[str] = None
    item_nombre: Optional[str] = None
    estado: str
    observacion: Optional[str] = None
    mecanico_id: Optional[int] = None
    mecanico_nombre: Optional[str] = None
    fecha_registro: datetime


class PautaBatchUpdateDTO(BaseModel):
    """Payload para envío y actualización en bloque de respuestas de pauta preventiva."""
    respuestas: List[PautaRespuestaCreateDTO]


class PautaEstadoResumenDTO(BaseModel):
    """Resumen consolidado del estado de completitud y defectos de la pauta preventiva."""
    total_items: int
    respondidos: int
    pendientes: int
    completado: bool
    items_con_defecto: int
    respuestas: List[PautaRespuestaDTO] = []
