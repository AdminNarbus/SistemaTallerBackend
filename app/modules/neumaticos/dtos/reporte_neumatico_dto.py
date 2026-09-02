from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class ReporteNeumaticoBaseDTO(BaseModel):
    usuario_id: Optional[int] = None
    bus_id: Optional[int] = None
    n_bus: Optional[str] = None
    tipo_bus: Optional[str] = None
    ruedas: Optional[Any] = None
    motivo: Optional[str] = None
    precio: Optional[float] = None
    marca_fuego: Optional[str] = None
    evidencia_url: Optional[str] = None



class ReporteNeumaticoCreateDTO(ReporteNeumaticoBaseDTO):
    maquina: Optional[str] = None


class ReporteNeumaticoResponseDTO(ReporteNeumaticoBaseDTO):
    id: int
    fecha_subida: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
