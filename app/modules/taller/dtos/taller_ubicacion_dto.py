from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CiudadCrearDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    nombre: str = Field(min_length=1, max_length=100)

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El nombre no puede estar vacío")
        return value.strip()


class CiudadDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str


class TallerCrearDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=200)
    ciudad_id: int = Field(gt=0)
    tipo: Literal["INTERNO", "EXTERNO"]

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El nombre no puede estar vacío")
        return value.strip()


class TallerActualizarDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    ciudad_id: Optional[int] = Field(None, gt=0)
    tipo: Optional[Literal["INTERNO", "EXTERNO"]] = None
    is_activo: Optional[bool] = None

    @model_validator(mode="after")
    def validar_cambios(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Indique campos no nulos para actualizar")
        if self.nombre is not None and not self.nombre.strip():
            raise ValueError("El nombre no puede estar vacío")
        return self


class TallerDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    ciudad_id: int
    tipo: str
    is_activo: bool


class TallerSnapshotDTO(BaseModel):
    id: int
    nombre: str
    ciudad: str
    tipo: str


class UbicacionEventoDTO(BaseModel):
    id: int
    version: Optional[int] = None
    taller_responsable: TallerSnapshotDTO
    talleres_colaboradores: list[TallerSnapshotDTO] = []
    registrado_por_id: Optional[int] = None
    registrado_por: Optional[str] = None
    registrado_en: Optional[str] = None
    operacion_id: Optional[str] = None
    motivo: Optional[str] = None


class CorregirUbicacionDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operacion_id: UUID
    ubicacion_esperada_id: Optional[int]
    taller_id: int = Field(gt=0)
    talleres_colaboradores_ids: list[int] = Field(default_factory=list)
    motivo: str = Field(min_length=1, max_length=2000)

    @field_validator("motivo")
    @classmethod
    def validar_motivo(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Debe indicar el motivo de la corrección")
        return value.strip()
