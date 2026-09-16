from datetime import datetime
from typing import Any, Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class BusBaseDTO(BaseModel):
    n_bus: Optional[str] = None
    patente: str
    marca: Optional[str] = None
    modelo: Optional[str] = None
    n_motor: Optional[str] = None
    n_chasis: Optional[str] = None
    n_carroceria: Optional[str] = None
    astos: Optional[str] = None
    anio: Optional[str] = None
    servicio: Optional[str] = None
    tipo_bus: Optional[str] = None
    empresa_id: Optional[int] = None
    clasificacion: Optional[str] = None
    min: Optional[Decimal] = None
    max: Optional[Decimal] = None
    tipo: Optional[str] = None
    max_litros: Optional[int] = None
    is_active: Optional[bool] = True
    en_taller: bool = False
    fecha_creacion: Optional[datetime] = None
    fecha_baja: Optional[datetime] = None
    motivo_baja: Optional[str] = None
    usuario_baja_id: Optional[int] = None

    @field_validator("en_taller", mode="before")
    @classmethod
    def validar_en_taller(cls, v: Any) -> bool:
        return bool(v) if v is not None else False


class BusResponseDTO(BusBaseDTO):
    id: int

    model_config = ConfigDict(from_attributes=True)


class BusCreateDTO(BaseModel):
    patente: str = Field(..., min_length=4, max_length=20, description="Patente del vehículo")
    n_bus: Optional[str] = Field(None, max_length=50, description="Número de máquina único")
    marca: Optional[str] = Field(None, max_length=100)
    modelo: Optional[str] = Field(None, max_length=100)
    n_motor: Optional[str] = None
    n_chasis: Optional[str] = None
    n_carroceria: Optional[str] = None
    astos: Optional[str] = None
    anio: Optional[str] = None
    servicio: Optional[str] = None
    tipo_bus: Optional[str] = None
    empresa_id: Optional[int] = None
    clasificacion: Optional[str] = None
    min: Optional[Decimal] = None
    max: Optional[Decimal] = None
    tipo: Optional[str] = None
    max_litros: Optional[int] = None
    en_taller: bool = False

    @field_validator("patente")
    @classmethod
    def normalizar_patente(cls, v: str) -> str:
        clean = v.strip().upper()
        if not clean:
            raise ValueError("La patente no puede estar vacía")
        return clean

    @field_validator("n_bus")
    @classmethod
    def normalizar_n_bus(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            return clean if clean else None
        return None


class BusDarDeBajaDTO(BaseModel):
    motivo: Optional[str] = Field(None, max_length=500, description="Motivo de la baja del bus")
    forzar: bool = Field(False, description="Forzar la baja aun si hay OTs abiertas en taller")


class BusAutocompleteDTO(BaseModel):
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
    id: int
    n_bus: str
    patente: Optional[str] = None
    en_taller: bool = False

    @field_validator("en_taller", mode="before")
    @classmethod
    def validar_en_taller(cls, v: Any) -> bool:
        return bool(v) if v is not None else False

    model_config = ConfigDict(from_attributes=True)


class BusUpdateEnTallerDTO(BaseModel):
    en_taller: bool
    motivo: Optional[str] = None

