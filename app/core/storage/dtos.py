"""
dtos.py
=======
Data Transfer Objects (DTOs) para la capa de almacenamiento de archivos.
"""
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class StorageUploadResultDTO(BaseModel):
    """
    DTO que encapsula el resultado exitoso de la subida de un archivo al almacenamiento.
    
    Provee compatibilidad dual:
    1. Acceso orientado a objetos: resultado.url, resultado.path, etc.
    2. Acceso como diccionario: resultado["url"], resultado.get("path"), "url" in resultado.
    """
    url: str = Field(..., description="URL accesible pública, relativa o firmada.")
    path: str = Field(..., description="Ruta canónica persistida en el bucket o directorio.")
    filename: str = Field(..., description="Nombre único generado para el archivo.")
    original_filename: str = Field(..., description="Nombre original del archivo subido por el cliente.")
    size_bytes: int = Field(..., description="Tamaño del archivo en bytes.")
    content_type: str = Field(..., description="Tipo MIME del archivo almacenado.")

    model_config = ConfigDict(frozen=True)

    def __getitem__(self, item: str) -> Any:
        """Permite acceso estilo diccionario para compatibilidad hacia atrás: dto['url']."""
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item: str, default: Optional[Any] = None) -> Any:
        """Permite método .get() estilo diccionario: dto.get('path')."""
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        """Permite operador 'in': 'url' in dto."""
        return item in self.model_fields


__all__ = ["StorageUploadResultDTO"]
