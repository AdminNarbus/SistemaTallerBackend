from typing import Optional
from pydantic import BaseModel
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO


class TokenDTO(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UsuarioResponseDTO] = None


class RefreshTokenRequestDTO(BaseModel):
    refresh_token: str


class TokenPayloadDTO(BaseModel):
    sub: Optional[int] = None
