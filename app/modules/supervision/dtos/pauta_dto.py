from typing import List
from pydantic import Field

from app.modules.formularios.dtos.pauta_dto import PautaProgresoDTO
from app.modules.taller.dtos.pauta_dto import PautaRespuestaDTO
from app.modules.taller.dtos.solicitud_dto import SolicitudDTO


class SolicitudDetalleSupervisionDTO(SolicitudDTO):
    """La ficha de supervisión solo expone el avance de la pauta."""

    pauta_respuestas: List[PautaRespuestaDTO] = Field(default_factory=list, exclude=True)
    pauta_resumen: PautaProgresoDTO
