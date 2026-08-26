from typing import Optional
from pydantic import BaseModel, ConfigDict


class UsuarioBase(BaseModel):
    username: str
    rol: Optional[str] = "CONDUCTOR"
    conductor_id: Optional[int] = None
    is_active: Optional[bool] = True


class UsuarioCreate(UsuarioBase):
    password: str


class UsuarioLogin(BaseModel):
    username: str
    password: str


class UsuarioResponse(UsuarioBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
