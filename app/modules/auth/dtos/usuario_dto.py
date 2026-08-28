from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UsuarioBaseDTO(BaseModel):
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=100)
    rol: Optional[str] = "CONDUCTOR"
    is_active: Optional[bool] = True


class UsuarioCreateDTO(UsuarioBaseDTO):
    password: str = Field(..., min_length=6, max_length=100)


class UsuarioResponseDTO(BaseModel):
    id: int
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    nombre_completo: Optional[str] = None
    rut: Optional[str] = None
    username: str
    rol: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class UsuarioLoginDTO(BaseModel):
    username: str
    password: str
