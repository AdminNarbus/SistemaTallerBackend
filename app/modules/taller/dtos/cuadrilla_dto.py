from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class SolicitudMecanicoDTO(BaseModel):
    """Representación de un mecánico trabajando activamente o con historial en una OT."""
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
    fecha_asignacion: Optional[datetime] = None
    fecha_desasignacion: Optional[datetime] = None


class TomarTrabajoDTO(BaseModel):
    """Payload para tomar una OT completa e invitar colaboradores."""
    colaboradores_ids: Optional[List[int]] = None
    colaboradores_nombres: Optional[List[str]] = None
    comentario_inicial: Optional[str] = None


class AutoasignarFallasDTO(BaseModel):
    """Payload para autoasignación atómica de averías específicas por un mecánico."""
    detalles_ids: List[int]
    comentario: Optional[str] = None
    colaboradores_ids: Optional[List[int]] = None


class AsignarFallasSupervisoraDTO(BaseModel):
    """Payload para asignación directa de averías a un mecánico por supervisión."""
    mecanico_id: int
    detalles_ids: List[int]
    comentario: Optional[str] = None


class TerminarAvanceDTO(BaseModel):
    """Payload para registrar fin de turno o avance en averías asignadas."""
    detalles_ids: Optional[List[int]] = None
    comentario: Optional[str] = None


class LiberarTurnoDTO(BaseModel):
    """Payload para liberar turno de cuadrilla completa hacia el siguiente turno."""
    comentario: Optional[str] = None


class AgregarColaboradorDTO(BaseModel):
    """Payload para invitar un colega mecánico al equipo de trabajo de la OT."""
    colaborador_id: Optional[int] = None
    colaborador_nombre: Optional[str] = None
