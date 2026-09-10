import asyncio
import logging
import os
from app.core.storage.base import BaseStorageProvider

logger = logging.getLogger(__name__)


def _write_bytes_to_disk(full_path: str, content: bytes) -> None:
    """Escritura síncrona en disco en un worker thread."""
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(content)


def _delete_file_from_disk(full_path: str) -> bool:
    """Eliminación síncrona de archivo en disco."""
    try:
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False
    except OSError as e:
        logger.warning("[STORAGE_LOCAL] Error al eliminar archivo '%s': %s", full_path, e)
        return False


class LocalStorageProvider(BaseStorageProvider):
    """
    Proveedor de almacenamiento local en disco.
    Guarda los archivos en el directorio local ./uploads/<folder>/
    y retorna la URL relativa accesible vía FastAPI StaticFiles: /uploads/<folder>/<filename>
    """

    def __init__(self, base_directory: str = "uploads"):
        self.base_directory = os.path.abspath(base_directory)
        os.makedirs(self.base_directory, exist_ok=True)

    async def upload_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        folder: str = "evidencias",
    ) -> str:
        folder_clean = folder.strip("/\\")
        target_dir = os.path.join(self.base_directory, folder_clean)
        full_path = os.path.join(target_dir, filename)

        await asyncio.to_thread(_write_bytes_to_disk, full_path, file_content)

        relative_url = f"/uploads/{folder_clean}/{filename}"
        logger.info(
            "[STORAGE_LOCAL] Archivo guardado en disco local | ruta='%s' | url='%s' | bytes=%d",
            full_path,
            relative_url,
            len(file_content),
        )
        return relative_url

    async def delete_file(self, file_url: str) -> bool:
        if not file_url.startswith("/uploads/"):
            return False
        relative_path = file_url.replace("/uploads/", "").strip("/\\")
        full_path = os.path.join(self.base_directory, relative_path)
        return await asyncio.to_thread(_delete_file_from_disk, full_path)
