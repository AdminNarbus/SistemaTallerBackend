from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


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


class BusCreateDTO(BusBaseDTO):
    pass


class BusResponseDTO(BusBaseDTO):
    id: int

    model_config = ConfigDict(from_attributes=True)


class BusAutocompleteDTO(BaseModel):
    id: int
    n_bus: Optional[str] = None
    patente: str
    marca: Optional[str] = None
    modelo: Optional[str] = None
    tipo_bus: Optional[str] = None
    is_active: Optional[bool] = True
    en_taller: bool = False

    model_config = ConfigDict(from_attributes=True)


class BusSimpleDTO(BaseModel):
    id: int
    n_bus: str
    patente: Optional[str] = None
    en_taller: bool = False

    model_config = ConfigDict(from_attributes=True)


class BusSearchPayloadDTO(BaseModel):
    query: Optional[str] = None


class BusUpdateEnTallerDTO(BaseModel):
    en_taller: bool
    motivo: Optional[str] = None


