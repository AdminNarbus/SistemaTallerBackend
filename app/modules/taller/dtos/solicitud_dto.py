from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.taller.dtos.averias_dto import SolicitudDetalleCreateDTO, SolicitudDetalleDTO
from app.modules.taller.dtos.bitacora_dto import SolicitudComentarioDTO
from app.modules.taller.dtos.cuadrilla_dto import SolicitudMecanicoDTO
from app.modules.taller.dtos.pauta_dto import PautaRespuestaDTO


class SolicitudEvidenciaDTO(BaseModel):
    """Metadatos de una fotografía o evidencia adjunta a la orden de trabajo."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    detalle_id: Optional[int] = None
    usuario_id: Optional[int] = None
    comentario_id: Optional[int] = None
    url: str
    original_filename: Optional[str] = None
    size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    fecha_creacion: Optional[datetime] = None


class EstadiaTallerDTO(BaseModel):
    """Registro inmutable de una visita física a taller (ingreso y egreso)."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    solicitud_id: Optional[int] = None
    numero_visita: int
    fecha_ingreso: datetime
    fecha_salida: Optional[datetime] = None
    horas_estadia: Optional[float] = None
    motivo_salida: Optional[str] = None


class SolicitudCreateDTO(BaseModel):
    """Payload de entrada para creación de una orden de trabajo."""
    n_bus: Optional[str] = None
    bus_id: Optional[int] = None
    bus_patente: Optional[str] = None
    descripcion_general: Optional[str] = None
    foto_url: Optional[str] = None
    fotos_urls: Optional[List[str]] = None
    detalles: Optional[List[SolicitudDetalleCreateDTO]] = None
    ingreso_inmediato_taller: Optional[bool] = Field(
        None,
        description="Indica si el bus ingresa inmediatamente al taller físico (bus.en_taller = True). Por defecto True si lo crea un supervisor o admin.",
    )

    @model_validator(mode="after")
    def check_bus_identifier(self):
        if not self.n_bus and not self.bus_id:
            raise ValueError("Debe proporcionar al menos 'bus_id' o 'n_bus'")
        return self


class SolicitudDTO(BaseModel):
    """Ficha canónica integral de una orden de trabajo (OT) de taller."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    n_bus: str
    bus_id: Optional[int] = None
    bus_patente: Optional[str] = None
    usuario_creador_id: Optional[int] = None
    usuario_creador_nombre: Optional[str] = None
    usuario_creador_telefono: Optional[str] = None
    mecanico_cierre_id: Optional[int] = None
    mecanico_cierre_nombre: Optional[str] = None
    estado: str
    descripcion_general: Optional[str] = None
    foto_url: Optional[str] = None
    motivo_incompleto_checklist: Optional[str] = None
    motivo_cierre_parcial: Optional[str] = None
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    fecha_liberacion: Optional[datetime] = None
    fecha_primer_ingreso_taller: Optional[datetime] = None
    horas_demora_primer_ingreso: Optional[float] = None
    horas_taller_acumuladas: Optional[float] = 0.0
    total_visitas: int = 0
    horas_en_taller: Optional[float] = None
    reincidencias_30d: Optional[int] = 0

    pauta_completada: bool = False
    total_fallas: int = 0
    fallas_resueltas: int = 0
    fallas_incompletas: int = 0
    fallas_con_falta_repuesto: int = 0
    fallas_pendientes: int = 0

    detalles: List[SolicitudDetalleDTO] = []
    mecanicos: List[SolicitudMecanicoDTO] = []
    historial_mecanicos: List[SolicitudMecanicoDTO] = []
    comentarios: List[SolicitudComentarioDTO] = []
    pauta_respuestas: List[PautaRespuestaDTO] = []
    evidencias: List[SolicitudEvidenciaDTO] = []
    estadias: List[EstadiaTallerDTO] = []


class SolicitudResumenDTO(BaseModel):
    """
    DTO ultraligero para listados de alta velocidad del mecánico (Bandeja de Pendientes y Mis Trabajos)
    y vista de auditoría para la supervisora.
    Optimizado para devolver exclusivamente los campos esenciales de la tarjeta/fila.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Número identificador de la OT (numero_ot)")
    estado: str = Field(..., description="Estado actual de la orden de trabajo")
    n_bus: str = Field(..., description="Número de bus")
    fecha_ingreso: Optional[datetime] = Field(
        None, description="Fecha de ingreso al taller (fecha_primer_ingreso_taller o fecha_creacion)"
    )
    fecha_actualizacion: Optional[datetime] = Field(
        None, description="Fecha de última modificación de la orden de trabajo (fecha_actualizacion)"
    )
    chofer: Optional[str] = Field(
        None, description="Nombre del conductor/usuario que generó la OT (usuario_creador_nombre)"
    )
    tiempo_taller: Optional[float] = Field(
        None, description="Tiempo transcurrido en taller en horas (horas_en_taller / horas_taller_acumuladas)"
    )
    numero_fallas: int = Field(
        0, description="Número de fallas contextual: en pendientes son las disponibles sin resolver, en mis trabajos son las asignadas al mecánico"
    )
    fallas_asignadas_al_mecanico: int = Field(
        0,
        description="Fallas pendientes o incompletas con una asignación activa para el mecánico autenticado en mis trabajos",
    )

