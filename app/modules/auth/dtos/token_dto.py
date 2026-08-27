from typing import Optional
from pydantic import BaseModel
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO


class TokenDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional[UsuarioResponseDTO] = None


class TokenPayloadDTO(BaseModel):
    sub: Optional[int] = None
