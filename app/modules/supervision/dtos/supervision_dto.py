from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from app.modules.supervision.constants import TipoAlertaSupervision, SeveridadAlerta


class MetricasEstadoDTO(BaseModel):
    total_solicitudes: int = Field(0, description="Total histórico/activo de solicitudes de taller")
    reportadas: int = Field(0, description="Solicitudes en estado REPORTADO")
    pendientes: int = Field(0, description="Solicitudes en estado PENDIENTE")
    en_reparacion: int = Field(0, description="Solicitudes en estado EN_REPARACION")
    liberadas: int = Field(0, description="Solicitudes en estado LIBERADO con averías pendientes")
    finalizadas: int = Field(0, description="Solicitudes en estado FINALIZADO")
    buses_fisicamente_en_taller: int = Field(0, description="Buses de la flota marcados con en_taller = True")
    fallas_bloqueadas_por_repuesto: int = Field(0, description="Fallas activas que reportan falta de repuestos")


class CategoriaFrecuenciaDTO(BaseModel):
    categoria_id: Optional[int] = None
    categoria_nombre: str
    total_fallas: int


class MecanicoCargaDTO(BaseModel):
    id: int = Field(..., description="ID del mecánico")
    nombre_completo: str = Field(..., description="Nombre y apellido del mecánico")
    username: str = Field(..., description="Nombre de usuario del mecánico")
    fallas_activas_count: int = Field(0, description="Cantidad de fallas activas asignadas")
    disponible: bool = Field(True, description="True si no tiene fallas activas asignadas")


class AlertaSupervisionDTO(BaseModel):
    tipo: TipoAlertaSupervision | str = Field(..., description="TIEMPO_EN_TALLER_EXCEDIDO | LIBERADO_TIEMPO_EXCEDIDO | REPUESTO_FALTANTE | DEFECTO_PAUTA | BUS_SIN_MECANICOS")
    severidad: SeveridadAlerta | str = Field(SeveridadAlerta.MEDIA, description="BAJA | MEDIA | ALTA | CRITICA")
    solicitud_id: int
    n_bus: str
    mensaje: str
    horas_acumuladas: Optional[float] = Field(None, description="Horas acumuladas en el estado o en taller")
    detalle_id: Optional[int] = None
    fecha_deteccion: datetime = Field(default_factory=datetime.now)


class ResumenTallerDTO(BaseModel):
    fecha_generacion: datetime = Field(default_factory=datetime.now)
    metricas_estado: MetricasEstadoDTO
    porcentaje_resolucion_fallas: float = Field(0.0, description="Porcentaje de fallas marcadas como resueltas")
    total_fallas_registradas: int = Field(0, description="Cantidad total de detalles de fallas en taller")
    total_fallas_resueltas: int = Field(0, description="Cantidad de detalles de fallas resueltas")
    fallas_por_categoria: List[CategoriaFrecuenciaDTO] = Field(default_factory=list)
    buses_activos_taller: List[str] = Field(default_factory=list, description="Lista de n_bus actualmente en órdenes abiertas")
    alertas: List[AlertaSupervisionDTO] = Field(default_factory=list, description="Alertas activas de supervisión de taller")

