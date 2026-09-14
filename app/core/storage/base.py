from abc import ABC, abstractmethod
from typing import BinaryIO, Union


class BaseStorageProvider(ABC):
    """
    Interfaz abstracta para proveedores de almacenamiento de archivos.
    Permite intercambiar implementaciones (Google Cloud Storage, Local Disk, S3, etc.)
    sin acoplar la lógica de negocio a un SDK específico.
    """

    @abstractmethod
    async def upload_file(
        self,
        file_content: Union[bytes, BinaryIO],
        filename: str,
        content_type: str,
        folder: str = "evidencias",
    ) -> str:
        """
        Sube un archivo al almacenamiento persistente.
        
        Args:
            file_content: Bytes del archivo a almacenar.
            filename: Nombre único del archivo en el almacenamiento.
            content_type: Tipo MIME del archivo (ej. image/jpeg).
            folder: Carpeta o prefijo dentro del almacenamiento (ej. 'evidencias', 'mantencion').
            
        Returns:
            str: URL pública o accesible del archivo almacenado.
        """
        pass

    @abstractmethod
    async def delete_file(self, file_url: str) -> bool:
        """
        Elimina un archivo del almacenamiento persistente a partir de su URL.
        
        Args:
            file_url: URL pública del archivo a eliminar.
            
        Returns:
            bool: True si se eliminó con éxito, False en caso contrario.
        """
        pass

    @abstractmethod
    def get_url(self, file_path_or_url: str, expiration_minutes: int = 60) -> str:
        """
        Genera o resuelve la URL accesible (pública, relativa o firmada temporal)
        para un recurso dado su path canónico o URL previa.
        
        Args:
            file_path_or_url: Ruta relativa (ej. 'solicitudes/uuid.jpg') o URL almacenada.
            expiration_minutes: Minutos de vigencia si es una URL firmada (default 60 min).
            
        Returns:
            str: URL lista para ser consumida por el cliente frontend.
        """
        pass


__all__ = ["BaseStorageProvider"]


