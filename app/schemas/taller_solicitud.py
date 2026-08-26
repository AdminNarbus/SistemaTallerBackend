from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict


class ItemSolicitud(BaseModel):
    id: Optional[int] = None
    nombre: Optional[str] = None
    resuelto: Optional[str] = "NO"


class SolicitudMantencionCreate(BaseModel):
    usuario_id: Optional[int] = None
    id_bus: Optional[int] = None
    n_bus: str
    descripcion: Optional[str] = None
    items: Optional[List[Any]] = None
    foto_base64: Optional[str] = None
    estado: Optional[str] = "PENDIENTE"


class SolicitudMantencionResponse(BaseModel):
    id: int
    usuario_id: Optional[int] = None
    id_bus: Optional[int] = None
    n_bus: str
    descripcion: Optional[str] = None
    items: Optional[List[Any]] = None
    foto_url: Optional[str] = None
    estado: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
