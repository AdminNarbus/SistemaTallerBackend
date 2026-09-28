from typing import Optional
from pydantic import BaseModel


class BusUpdateEnTallerDTO(BaseModel):
    """Payload para actualizar el estado físico en taller de un bus."""

    en_taller: bool
    motivo: Optional[str] = None
