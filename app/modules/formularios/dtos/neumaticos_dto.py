import json
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReporteNeumaticoBaseDTO(BaseModel):
    usuario_id: Optional[int] = None
    bus_id: Optional[int] = None
    n_bus: Optional[str] = None
    ruedas: Optional[Any] = None
    motivo: Optional[str] = None
    marca_fuego: Optional[str] = None
    evidencia_url: Optional[str] = None


class ReporteNeumaticoCreateDTO(ReporteNeumaticoBaseDTO):
    maquina: Optional[str] = None
    ruedas: list[dict[str, Any] | str | int] = Field(..., min_length=1, max_length=1)
    marca_fuego: Optional[str] = Field(None, max_length=100)

    @field_validator("ruedas", mode="before")
    @classmethod
    def validar_neumatico_unico(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                # El formulario también envía posiciones simples, por ejemplo "Rueda 4".
                if value.lstrip().startswith(("[", "{")):
                    raise ValueError("ruedas debe contener JSON válido")
        if isinstance(value, (dict, str, int)) and not isinstance(value, bool):
            value = [value]
        if not isinstance(value, list) or len(value) != 1:
            raise ValueError("Cada reporte debe indicar exactamente un neumático")
        rueda = value[0]
        if isinstance(rueda, bool) or not isinstance(rueda, (dict, str, int)) or not rueda:
            raise ValueError("El neumático debe tener una identificación válida")
        if isinstance(rueda, str) and not rueda.strip():
            raise ValueError("El neumático no puede estar vacío")
        if isinstance(rueda, int) and rueda <= 0:
            raise ValueError("La posición del neumático debe ser positiva")
        return value

    @field_validator("marca_fuego", mode="before")
    @classmethod
    def normalizar_marca_fuego(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class ReporteNeumaticoResponseDTO(BaseModel):
    id: int
    usuario_id: Optional[int] = None
    bus_id: Optional[int] = None
    n_bus: Optional[str] = None
    tipo_bus: Optional[str] = None
    ruedas: Optional[Any] = None
    motivo: Optional[str] = None
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


class ReporteNeumaticoPaginadoDTO(BaseModel):
    items: list[ReporteNeumaticoResponseDTO] = Field(default_factory=list, description="Listado de reportes")
    total: int = Field(0, description="Total de reportes encontrados")
    page: int = Field(1, description="Página actual")
    page_size: int = Field(20, description="Cantidad de elementos por página")
    pages: int = Field(0, description="Total de páginas calculadas")
