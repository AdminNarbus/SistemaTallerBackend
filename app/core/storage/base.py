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
