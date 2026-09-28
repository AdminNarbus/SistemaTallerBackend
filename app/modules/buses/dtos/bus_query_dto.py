from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, field_validator


class BusAutocompleteDTO(BaseModel):
    """DTO optimizado para respuestas rápidas de selección y autocompletado de buses."""

    id: int
    n_bus: Optional[str] = None
    patente: str
    marca: Optional[str] = None
    modelo: Optional[str] = None
    tipo_bus: Optional[str] = None
    is_active: Optional[bool] = True
    en_taller: bool = False

    @field_validator("en_taller", mode="before")
    @classmethod
    def validar_en_taller(cls, v: Any) -> bool:
        return bool(v) if v is not None else False

    model_config = ConfigDict(from_attributes=True)


class BusSimpleDTO(BaseModel):
    """DTO mínimo y ligero para componentes de búsqueda de flota en taller."""

    id: int
    n_bus: str
    patente: Optional[str] = None
    en_taller: bool = False

    @field_validator("en_taller", mode="before")
    @classmethod
    def validar_en_taller(cls, v: Any) -> bool:
        return bool(v) if v is not None else False

    model_config = ConfigDict(from_attributes=True)
