from typing import Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class BusSearchPayload(BaseModel):
    n_bus: Optional[Union[str, int]] = Field(
        default=None,
        description="Número o prefijo de bus a buscar (ej: 3, '12'). Si se envía vacío o null, retorna todos los buses.",
    )
    numero: Optional[Union[str, int]] = Field(
        default=None,
        description="Alias opcional para n_bus",
    )
    q: Optional[Union[str, int]] = Field(
        default=None,
        description="Alias opcional para el parámetro de búsqueda",
    )

    def get_search_term(self) -> Optional[str]:
        """Obtiene el término de búsqueda limpio prioritariamente desde n_bus, numero o q."""
        for val in (self.n_bus, self.numero, self.q):
            if val is not None:
                s_val = str(val).strip()
                if s_val:
                    return s_val
        return None


class BusResponse(BaseModel):
    id: int
    n_bus: Optional[str] = None
    patente: Optional[str] = None
    tipo_bus: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
