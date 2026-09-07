from datetime import datetime
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class ReporteNeumaticoBaseDTO(BaseModel):
    usuario_id: Optional[int] = None
    bus_id: Optional[int] = None
    n_bus: Optional[str] = None
    tipo_bus: Optional[str] = None
    ruedas: Optional[Any] = None
    motivo: Optional[str] = None
    precio: Optional[Union[float, str]] = None
    marca_fuego: Optional[str] = None
    evidencia_url: Optional[str] = None


class ReporteNeumaticoCreateDTO(ReporteNeumaticoBaseDTO):
    maquina: Optional[str] = None


class ReporteNeumaticoResponseDTO(BaseModel):
    id: int
    usuario_id: Optional[int] = None
    bus_id: Optional[int] = None
    n_bus: Optional[str] = None
    tipo_bus: Optional[str] = None
    ruedas: Optional[Any] = None
    motivo: Optional[str] = None
    precio: Optional[float] = None
    marca_fuego: Optional[str] = None
    evidencia_url: Optional[str] = None
    fecha_subida: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FormularioNeumaticoStatusDTO(BaseModel):
    status: str = "success"
    message: str = "Solicitud de formularioNeumatico recibida correctamente"
    data: Optional[Any] = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


class FormularioNeumaticoResponseDTO(BaseModel):
    status: str = "success"
    message: str = "Formulario de neumáticos procesado y guardado exitosamente"
    reporte_id: Optional[int] = None
    bus_id: Optional[int] = None
    resumen: str
    datos_recibidos: Dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)
