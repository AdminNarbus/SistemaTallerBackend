from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


# --- Categoria Falla DTOs ---
class CategoriaFallaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    is_active: bool


# --- Falla Taller DTOs ---
class FallaTallerDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria_id: int
    nombre: str
    is_active: bool
    categoria: Optional[CategoriaFallaDTO] = None


# --- Detalle Falla DTOs ---
class SolicitudDetalleCreateDTO(BaseModel):
    falla_id: Optional[int] = None
    descripcion_personalizada: Optional[str] = None


class SolicitudDetalleDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    falla_id: Optional[int] = None
    falla: Optional[FallaTallerDTO] = None
    descripcion_personalizada: Optional[str] = None
    resuelto: bool
    mecanico_resolvio_id: Optional[int] = None
    mecanico_resolvio_nombre: Optional[str] = None
    fecha_creacion: datetime
    fecha_resolucion: Optional[datetime] = None


# --- Mecanico Asignado DTOs ---
class SolicitudMecanicoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    mecanico_id: int
    mecanico_nombre: Optional[str] = None
    es_lider_responsable: bool
    is_activo: bool
    fecha_asignacion: datetime
    fecha_desasignacion: Optional[datetime] = None


# --- Comentario Bitácora DTOs ---
class ComentarioCreateDTO(BaseModel):
    comentario: str
    tipo: Optional[str] = "GENERAL"


class SolicitudComentarioDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    usuario_id: int
    usuario_nombre: Optional[str] = None
    tipo: str
    comentario: str
    fecha_registro: datetime


# --- Solicitud Principales DTOs ---
class SolicitudCreateDTO(BaseModel):
    n_bus: str
    descripcion_general: Optional[str] = None
    foto_url: Optional[str] = None
    detalles: Optional[List[SolicitudDetalleCreateDTO]] = None


class TomarTrabajoDTO(BaseModel):
    colaboradores_ids: Optional[List[int]] = None
    colaboradores_nombres: Optional[List[str]] = None
    comentario_inicial: Optional[str] = None


class LiberarTurnoDTO(BaseModel):
    comentario: Optional[str] = None


class FinalizarSolicitudDTO(BaseModel):
    comentario_cierre: Optional[str] = None


class SolicitudDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    n_bus: str
    usuario_creador_id: Optional[int] = None
    usuario_creador_nombre: Optional[str] = None
    mecanico_cierre_id: Optional[int] = None
    mecanico_cierre_nombre: Optional[str] = None
    estado: str
    descripcion_general: Optional[str] = None
    foto_url: Optional[str] = None
    fecha_creacion: datetime
    fecha_cierre: Optional[datetime] = None

    detalles: List[SolicitudDetalleDTO] = []
    mecanicos: List[SolicitudMecanicoDTO] = []
    comentarios: List[SolicitudComentarioDTO] = []
