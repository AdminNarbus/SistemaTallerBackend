from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from app.modules.mantencion.dtos.mantencion_dto import SolicitudDTO


class MetricasEstadoDTO(BaseModel):
    total_solicitudes: int = Field(0, description="Total histórico/activo de solicitudes de taller")
    reportadas: int = Field(0, description="Solicitudes en estado REPORTADO")
    en_reparacion: int = Field(0, description="Solicitudes en estado EN_REPARACION")
    pendiente_reasignacion: int = Field(0, description="Solicitudes en estado PENDIENTE_REASIGNACION")
    finalizadas: int = Field(0, description="Solicitudes en estado FINALIZADO")


class CategoriaFrecuenciaDTO(BaseModel):
    categoria_id: Optional[int] = None
    categoria_nombre: str
    total_fallas: int


class ResumenTallerDTO(BaseModel):
    fecha_generacion: datetime = Field(default_factory=datetime.now)
    metricas_estado: MetricasEstadoDTO
    porcentaje_resolucion_fallas: float = Field(0.0, description="Porcentaje de fallas marcadas como resueltas")
    total_fallas_registradas: int = Field(0, description="Cantidad total de detalles de fallas en taller")
    total_fallas_resueltas: int = Field(0, description="Cantidad de detalles de fallas resueltas")
    fallas_por_categoria: List[CategoriaFrecuenciaDTO] = Field(default_factory=list)
    buses_activos_taller: List[str] = Field(default_factory=list, description="Lista de n_bus actualmente en taller")
