from typing import Optional
from pydantic import BaseModel, ConfigDict


class CategoriaFallaDTO(BaseModel):
    """Representación de una categoría de fallas de taller."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    is_active: bool
    falla_id: Optional[int] = None
    falla_nombre: Optional[str] = None


class FallaTallerDTO(BaseModel):
    """Representación de una avería o falla del catálogo maestro de maestranza."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria_id: int
    nombre: str
    is_active: bool
    categoria: Optional[CategoriaFallaDTO] = None
