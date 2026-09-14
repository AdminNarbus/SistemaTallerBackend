from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.auth.constants import RolUsuario


class UsuarioBaseDTO(BaseModel):
    nombre: Optional[str] = Field(None, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    username: str = Field(..., min_length=3, max_length=100)
    rol: Optional[RolUsuario] = RolUsuario.CONDUCTOR
    is_active: Optional[bool] = True

    @field_validator("username", mode="before")
    @classmethod
    def validar_username(cls, v: Any) -> str:
        if isinstance(v, str):
            v_clean = v.strip()
            if not v_clean:
                raise ValueError("El username no puede estar vacío.")
            return v_clean
        return v

    @field_validator("nombre", "apellido", mode="before")
    @classmethod
    def sanitizar_nombres(cls, v: Any) -> Optional[str]:
        if isinstance(v, str):
            v_clean = v.strip()
            return v_clean if v_clean else None
        return v

    @field_validator("rol", mode="before")
    @classmethod
    def validar_rol(cls, v: Any) -> RolUsuario:
        if v is None:
            return RolUsuario.CONDUCTOR
        if isinstance(v, RolUsuario):
            return v
        if isinstance(v, str):
            rol_clean = v.strip().upper()
            if rol_clean in RolUsuario.__members__:
                return RolUsuario[rol_clean]
        raise ValueError(f"Rol '{v}' no es válido. Roles permitidos: {[r.value for r in RolUsuario]}")


class UsuarioCreateDTO(UsuarioBaseDTO):
    password: str = Field(..., min_length=6, max_length=100)

    @field_validator("password", mode="before")
    @classmethod
    def validar_password(cls, v: Any) -> str:
        if isinstance(v, str):
            v_clean = v.strip()
            if not v_clean:
                raise ValueError("La contraseña no puede estar vacía.")
            return v_clean
        return v


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
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)

    @field_validator("username", "password", mode="before")
    @classmethod
    def validar_no_vacio(cls, v: Any) -> str:
        if isinstance(v, str):
            v_clean = v.strip()
            if not v_clean:
                raise ValueError("El campo no puede estar vacío.")
            return v_clean
        return v

