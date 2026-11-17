import re
from typing import Literal

from pydantic import BaseModel, Field, StrictBool, field_validator


def normalizar_rut(value: str) -> str:
    return value.strip().replace(".", "").upper()


class ConductorExternoDTO(BaseModel):
    rut: str
    nombre: str = Field(min_length=1, max_length=100)
    apellido: str | None = Field(default=None, max_length=100)
    activo: StrictBool

    @field_validator("rut")
    @classmethod
    def validar_rut(cls, value: str) -> str:
        value = normalizar_rut(value)
        if not re.fullmatch(r"[0-9]{7,8}-[0-9K]", value):
            raise ValueError("RUT debe contener cuerpo numérico y dígito verificador con guion")
        return value


class ConductorSyncResponseDTO(BaseModel):
    periodo: str
    estado: Literal["completado", "ya_ejecutado"] = "completado"
    recibidos: int = 0
    creados: int = 0
    actualizados: int = 0
    habilitados: int = 0
    inhabilitados: int = 0
    sin_cambios: int = 0
    omitidos_otro_rol: int = 0
