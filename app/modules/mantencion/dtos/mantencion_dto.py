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


# --- Asignación Atómica de Fallas DTOs ---
class MecanicoAsignadoDTO(BaseModel):
    id: int
    nombre: str
    origen: str = "SUPERVISOR"
    asignado_por_id: Optional[int] = None
    asignado_por_nombre: Optional[str] = None
    fecha_asignacion: datetime


class AsignacionFallaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    detalle_id: int
    mecanico_id: int
    mecanico_nombre: Optional[str] = None
    asignado_por_id: Optional[int] = None
    asignado_por_nombre: Optional[str] = None
    origen: str
    is_activo: bool
    fecha_asignacion: datetime
    fecha_desasignacion: Optional[datetime] = None
    resuelto_en_esta_asignacion: bool
    duracion_minutos: Optional[int] = None
    comentario: Optional[str] = None


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
    falta_repuesto: bool = False
    comentario_repuesto: Optional[str] = None
    fecha_creacion: datetime
    fecha_resolucion: Optional[datetime] = None
    mecanicos_asignados: List[MecanicoAsignadoDTO] = []
    historial_asignaciones: List[AsignacionFallaDTO] = []


# --- Mecanico Asignado Global DTOs ---
class SolicitudMecanicoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    mecanico_id: int
    mecanico_nombre: Optional[str] = None
    asignado_por_id: Optional[int] = None
    asignado_por_nombre: Optional[str] = None
    duracion_minutos: Optional[int] = None
    es_lider_responsable: bool = False
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
    bus_id: Optional[int] = None
    descripcion_general: Optional[str] = None
    foto_url: Optional[str] = None
    detalles: Optional[List[SolicitudDetalleCreateDTO]] = None


class AutoasignarFallasDTO(BaseModel):
    detalles_ids: List[int]
    comentario: Optional[str] = None


class AsignarFallasSupervisoraDTO(BaseModel):
    mecanico_id: int
    detalles_ids: List[int]
    comentario: Optional[str] = None


class TerminarAvanceDTO(BaseModel):
    detalles_ids: Optional[List[int]] = None
    comentario: Optional[str] = None


# --- Falta de Repuesto DTOs ---
class ReportarRepuestoDTO(BaseModel):
    falta_repuesto: bool = True
    comentario: Optional[str] = None


# --- Pauta de Taller Preventiva DTOs ---
class PautaTallerItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria: str
    item: str
    orden: int
    is_active: bool


class PautaRespuestaCreateDTO(BaseModel):
    item_id: int
    estado: str  # 'OK' | 'DEFECTO' | 'NO_APLICA'
    observacion: Optional[str] = None


class PautaRespuestaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    item_id: int
    item_categoria: Optional[str] = None
    item_nombre: Optional[str] = None
    estado: str
    observacion: Optional[str] = None
    mecanico_id: Optional[int] = None
    mecanico_nombre: Optional[str] = None
    fecha_registro: datetime


class PautaBatchUpdateDTO(BaseModel):
    respuestas: List[PautaRespuestaCreateDTO]


class PautaEstadoResumenDTO(BaseModel):
    total_items: int
    respondidos: int
    pendientes: int
    completado: bool
    items_con_defecto: int
    respuestas: List[PautaRespuestaDTO] = []


class TomarTrabajoDTO(BaseModel):
    colaboradores_ids: Optional[List[int]] = None
    colaboradores_nombres: Optional[List[str]] = None
    comentario_inicial: Optional[str] = None


class LiberarTurnoDTO(BaseModel):
    comentario: Optional[str] = None


class FinalizarSolicitudDTO(BaseModel):
    comentario_cierre: Optional[str] = None
    motivo_incompleto_checklist: Optional[str] = None
    motivo_cierre_parcial: Optional[str] = None
    liberar_bus_taller: bool = True


class LiberarSolicitudDTO(FinalizarSolicitudDTO):
    pass


class AgregarColaboradorDTO(BaseModel):
    colaborador_id: Optional[int] = None
    colaborador_nombre: Optional[str] = None


class SolicitudDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    n_bus: str
    bus_id: Optional[int] = None
    bus_patente: Optional[str] = None
    usuario_creador_id: Optional[int] = None
    usuario_creador_nombre: Optional[str] = None
    mecanico_cierre_id: Optional[int] = None
    mecanico_cierre_nombre: Optional[str] = None
    estado: str
    descripcion_general: Optional[str] = None
    foto_url: Optional[str] = None
    motivo_incompleto_checklist: Optional[str] = None
    motivo_cierre_parcial: Optional[str] = None
    fecha_creacion: datetime
    fecha_cierre: Optional[datetime] = None

    pauta_completada: bool = False
    total_fallas: int = 0
    fallas_resueltas: int = 0
    fallas_con_falta_repuesto: int = 0

    detalles: List[SolicitudDetalleDTO] = []
    mecanicos: List[SolicitudMecanicoDTO] = []
    comentarios: List[SolicitudComentarioDTO] = []
    pauta_respuestas: List[PautaRespuestaDTO] = []



