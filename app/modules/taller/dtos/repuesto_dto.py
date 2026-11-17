"""Contratos del catálogo y del uso de repuestos."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RepuestoCrearDTO(BaseModel):
    codigo: str = Field(min_length=1, max_length=100)
    nombre: str = Field(min_length=1, max_length=300)
    parte: Optional[str] = Field(default=None, max_length=150)
    unidad: Optional[str] = Field(default=None, max_length=50)
    precio: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    iva: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    clasificacion: Optional[str] = Field(default=None, max_length=150)
    clasificacion_1: Optional[str] = Field(default=None, max_length=150)
    modelo: Optional[str] = Field(default=None, max_length=150)
    is_active: bool = True


class RepuestoActualizarDTO(BaseModel):
    codigo: Optional[str] = Field(default=None, min_length=1, max_length=100)
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=300)
    parte: Optional[str] = Field(default=None, max_length=150)
    unidad: Optional[str] = Field(default=None, max_length=50)
    precio: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    iva: Optional[Decimal] = Field(default=None, ge=0, max_digits=16, decimal_places=4)
    clasificacion: Optional[str] = Field(default=None, max_length=150)
    clasificacion_1: Optional[str] = Field(default=None, max_length=150)
    modelo: Optional[str] = Field(default=None, max_length=150)
    is_active: Optional[bool] = None


class RepuestoDTO(RepuestoCrearDTO):
    model_config = ConfigDict(from_attributes=True)
    id: int


class RegistrarRepuestoUtilizadoDTO(BaseModel):
    repuesto_id: int = Field(gt=0)
    cantidad: Decimal = Field(gt=0, max_digits=16, decimal_places=4)
    operacion_id: UUID


class AnularRepuestoUtilizadoDTO(BaseModel):
    motivo: str = Field(min_length=1, max_length=1000)
    operacion_id: UUID


class RepuestoUtilizadoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    falla_detalle_id: int
    repuesto_id: int
    cantidad_utilizada: Decimal
    unidad_al_registrar: Optional[str]
    usuario_registro_id: int
    codigo_repuesto_al_registrar: str
    nombre_repuesto_al_registrar: str
    parte_repuesto_al_registrar: Optional[str]
    nombre_usuario_al_registrar: str
    created_at: datetime
    fecha_anulacion: Optional[datetime]
    usuario_anulacion_id: Optional[int]
    nombre_usuario_al_anular: Optional[str]
    motivo_anulacion: Optional[str]
    solicitud_id: int
    bus_id: Optional[int]
    n_bus: str

    @field_validator("created_at", "fecha_anulacion")
    @classmethod
    def normalizar_fecha_utc(cls, valor: Optional[datetime]) -> Optional[datetime]:
        if valor is None:
            return None
        if valor.tzinfo is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc)
