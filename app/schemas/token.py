from typing import Optional
from pydantic import BaseModel
from app.schemas.usuario import UsuarioResponse


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional[UsuarioResponse] = None


class TokenPayload(BaseModel):
    sub: Optional[int] = None
