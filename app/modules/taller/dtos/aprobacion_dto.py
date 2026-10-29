from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AprobarSolicitudDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comentario: Optional[str] = Field(None, max_length=1000)
