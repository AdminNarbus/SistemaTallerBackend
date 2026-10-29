from typing import Optional

from pydantic import BaseModel, model_validator


class EstadoVisibleDTO(BaseModel):
    """El estado operativo solo se expone cuando la solicitud ya es una OT."""

    es_ot: bool = True
    estado: Optional[str] = None

    @model_validator(mode="after")
    def ocultar_estado_sin_aprobacion(self):
        if not self.es_ot:
            self.estado = None
        elif self.estado == "REPORTADO":
            self.estado = "PENDIENTE"
        return self
