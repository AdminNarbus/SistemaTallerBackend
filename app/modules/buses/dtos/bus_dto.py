from typing import Optional
from pydantic import BaseModel, ConfigDict


class BusBaseDTO(BaseModel):
    n_bus: str
    patente: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    is_active: Optional[bool] = True


class BusCreateDTO(BusBaseDTO):
    pass


class BusResponseDTO(BusBaseDTO):
    id: int

    model_config = ConfigDict(from_attributes=True)


class BusSearchPayloadDTO(BaseModel):
    query: Optional[str] = None
