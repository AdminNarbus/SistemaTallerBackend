from datetime import datetime
from typing import Annotated, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.modules.taller.dtos.pauta_revisor_dto import PautaMecanicoDTO, completar_revisores
from app.modules.taller.constants import EstadoItemPauta


class PautaTallerItemDTO(BaseModel):
    """Ítem del catálogo maestro de la pauta preventiva (10 ítems estándar)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria: str
    item: str
    orden: int
    is_active: bool


class PautaRespuestaCreateDTO(BaseModel):
    """Entrada individual para registrar el chequeo de un ítem de la pauta preventiva."""
    item_id: int
    estado: EstadoItemPauta
    observacion: Optional[str] = None

    @field_validator("estado", mode="before")
    @classmethod
    def normalizar_estado(cls, value: str) -> str:
        return "OK" if value == "BUENO" else value


class PautaRespuestaDTO(BaseModel):
    """Detalle de una respuesta guardada de pauta preventiva con trazabilidad del mecánico."""
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
    mecanicos_ids: List[int] = Field(default_factory=list)
    mecanicos: List[PautaMecanicoDTO] = Field(default_factory=list)

    _completar_revisores = model_validator(mode="before")(completar_revisores)


class PautaBatchUpdateDTO(BaseModel):
    """Payload para envío y actualización en bloque de respuestas de pauta preventiva."""
    respuestas: List[PautaRespuestaCreateDTO]


class PautaEstadoResumenDTO(BaseModel):
    """Resumen consolidado del estado de completitud y defectos de la pauta preventiva."""
    total_items: int
    respondidos: int
    pendientes: int
    completado: bool
    items_con_defecto: int
    respuestas: List[PautaRespuestaDTO] = []


class PautaProgresoDTO(BaseModel):
    revisadas: int
    total: int


class PautaPuntoDTO(PautaTallerItemDTO):
    revisado: bool
    respuesta: Optional[PautaRespuestaDTO] = None


class PautaGestionDTO(BaseModel):
    solicitud_id: int
    resumen: PautaProgresoDTO
    puntos: List[PautaPuntoDTO]


class PautaPuntoUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)
    estado: Optional[EstadoItemPauta] = Field(
        description="OK, DEFECTO o NO_APLICA para registrar revisión; null para devolver a pendiente."
    )
    observacion: Optional[str] = None
    mecanico_id: Optional[int] = Field(
        default=None, gt=0, description="Compatibilidad: un solo revisor. Usar este campo o mecanicos_ids."
    )
    mecanicos_ids: Optional[List[Annotated[int, Field(gt=0)]]] = Field(
        default=None, description="Lista de ejecutores del punto. Reemplaza la selección anterior."
    )

    @property
    def revisores_ids(self) -> List[int]:
        if self.mecanicos_ids is not None:
            return self.mecanicos_ids
        return [self.mecanico_id] if self.mecanico_id is not None else []


class PautaGestionUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    puntos: List[PautaPuntoUpdateDTO] = Field(min_length=1)
