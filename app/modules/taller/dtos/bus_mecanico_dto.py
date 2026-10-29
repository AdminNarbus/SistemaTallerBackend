from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.modules.taller.dtos.averias_dto import SolicitudDetalleCreateDTO
from app.modules.taller.constants import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.modules.taller.dtos.estado_visible_dto import EstadoVisibleDTO


class BusesMecanicoFiltroDTO(BaseModel):
    skip: int = Field(0, ge=0)
    limit: int = Field(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
    q: Optional[str] = Field(None, max_length=100)
    solo_activos: bool = True


class AgregarFallaBusDTO(SolicitudDetalleCreateDTO):
    """Reportar una falla al bus y, opcionalmente, comenzar a atenderla."""

    model_config = ConfigDict(extra="forbid")
    autoasignar: bool = Field(False, description="Asignar esta nueva falla al usuario que la reporta e iniciar su atención")


class OTBusMecanicoDTO(EstadoVisibleDTO):
    id: int
    creador_nombre: Optional[str] = None
    fecha_creacion: datetime
    numero_fallas_pendientes: int = 0


class BusMecanicoDTO(BaseModel):
    bus_id: int
    n_bus: Optional[str] = None
    ot: Optional[OTBusMecanicoDTO] = None
