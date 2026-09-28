from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.modules.taller.dtos.catalogo_dto import FallaTallerDTO


class MecanicoAsignadoDTO(BaseModel):
    """Representación resumida de un mecánico asignado a una avería particular."""
    id: int
    nombre: str
    origen: str = "SUPERVISOR"
    asignado_por_id: Optional[int] = None
    asignado_por_nombre: Optional[str] = None
    fecha_asignacion: Optional[datetime] = None


class AsignacionFallaDTO(BaseModel):
    """Registro histórico y de estado de asignación de una avería a un mecánico."""
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
    fecha_asignacion: Optional[datetime] = None
    fecha_desasignacion: Optional[datetime] = None
    resuelto_en_esta_asignacion: bool
    duracion_minutos: Optional[int] = None
    comentario: Optional[str] = None


class SolicitudDetalleCreateDTO(BaseModel):
    """Payload para reportar una avería al momento de crear una solicitud."""
    nombre: Optional[str] = Field(None, description="Nombre o texto directo de la avería (ej: 'Freno largo')")
    falla_nombre: Optional[str] = None
    descripcion_personalizada: Optional[str] = None
    falla_id: Optional[int] = None
    categoria_id: Optional[int] = None
    categoria_nombre: Optional[str] = None

    @property
    def texto_falla(self) -> str:
        """Retorna el nombre o descripción directa de la avería garantizando un valor limpio."""
        texto = self.nombre or self.falla_nombre or self.descripcion_personalizada or ""
        return texto.strip()


class AgregarFallaDTO(BaseModel):
    """Payload para añadir una avería adicional durante la atención en taller."""
    nombre: Optional[str] = Field(None, description="Nombre o texto directo de la avería")
    descripcion_personalizada: Optional[str] = None
    falla_nombre: Optional[str] = None
    categoria_id: Optional[int] = None
    falla_id: Optional[int] = None
    autoasignar: bool = True
    mecanico_asignado_id: Optional[int] = None
    mecanico_resolvio_id: Optional[int] = None
    mecanico_id: Optional[int] = None
    usuario_id: Optional[int] = None
    resuelto: bool = False

    @property
    def texto_falla(self) -> str:
        texto = self.nombre or self.descripcion_personalizada or self.falla_nombre or ""
        return texto.strip()

    @property
    def effective_resolutor_id(self) -> Optional[int]:
        return self.mecanico_resolvio_id or self.mecanico_id or self.usuario_id

    @property
    def effective_asignado_id(self) -> Optional[int]:
        return self.mecanico_asignado_id or (self.mecanico_id if not self.resuelto else None)


class CheckFallaDTO(BaseModel):
    """Payload para marcar o desmarcar la resolución de una avería desde taller o supervisión."""
    resuelto: bool = True
    mecanico_id: Optional[int] = Field(None, description="ID del mecánico resolutor")
    mecanico_resolvio_id: Optional[int] = Field(None, description="Alias para compatibilidad")
    usuario_id: Optional[int] = None
    comentario: Optional[str] = None

    @property
    def effective_mecanico_id(self) -> Optional[int]:
        return self.mecanico_id or self.mecanico_resolvio_id or self.usuario_id


ResolverFallaSupervisoraDTO = CheckFallaDTO


class ReportarRepuestoDTO(BaseModel):
    """Payload para reportar bloqueo de avería por falta de repuestos."""
    falta_repuesto: bool = True
    comentario: Optional[str] = None


class DetalleUpdateDTO(BaseModel):
    """Respuesta ultraligera tras check o reporte de repuesto (0 RTTs adicionales)."""
    detalle_id: int
    solicitud_id: int
    resuelto: bool
    falta_repuesto: bool
    mecanico_resolvio_id: Optional[int] = None
    mecanico_resolvio_nombre: Optional[str] = None
    comentario_repuesto: Optional[str] = None
    fecha_resolucion: Optional[datetime] = None


class SolicitudDetalleDTO(BaseModel):
    """Ficha completa de una avería asociada a una orden de trabajo."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    solicitud_id: int
    nombre: Optional[str] = None
    falla_nombre: Optional[str] = None
    categoria_id: Optional[int] = None
    categoria_nombre: Optional[str] = None
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

    def model_post_init(self, __context: Any) -> None:
        nombre_limpio = (
            self.descripcion_personalizada
            or self.falla_nombre
            or (self.falla.nombre if self.falla else None)
            or self.nombre
            or f"Avería #{self.id}"
        )
        if not self.nombre:
            self.nombre = nombre_limpio
        if not self.falla_nombre:
            self.falla_nombre = nombre_limpio
