import asyncio
import logging
import os
import shutil
from typing import BinaryIO, Optional, Union
from app.core.storage.base import BaseStorageProvider

logger = logging.getLogger(__name__)


def _write_file_to_disk(full_path: str, content: Union[bytes, BinaryIO]) -> None:
    """Escritura síncrona en disco en un worker thread."""
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if isinstance(content, bytes):
        with open(full_path, "wb") as f:
            f.write(content)
    else:
        with open(full_path, "wb") as f:
            shutil.copyfileobj(content, f)


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
    Proveedor de almacenamiento local en disco y volúmenes Cloud Run.
    Guarda los archivos en el directorio local o punto de montaje de volumen (/app/uploads)
    y retorna la URL relativa accesible vía FastAPI StaticFiles: /uploads/<folder>/<filename>
    """

    def __init__(self, base_directory: Optional[str] = None):
        if base_directory is None:
            from app.core.config import settings
            base_directory = getattr(settings, "UPLOAD_DIR", "uploads")
        self.base_directory = os.path.abspath(base_directory)
        os.makedirs(self.base_directory, exist_ok=True)

    async def upload_file(
        self,
        file_content: Union[bytes, BinaryIO],
        filename: str,
        content_type: str,
        folder: str = "evidencias",
    ) -> str:
        folder_clean = folder.strip("/\\")
        target_dir = os.path.join(self.base_directory, folder_clean)
        os.makedirs(target_dir, exist_ok=True)
        full_path = os.path.join(target_dir, filename)

        await asyncio.to_thread(_write_file_to_disk, full_path, file_content)

        relative_url = f"/uploads/{folder_clean}/{filename}"
        content_len = len(file_content) if isinstance(file_content, bytes) else -1
        logger.info(
            "[STORAGE_LOCAL] Archivo guardado en disco/volumen | ruta='%s' | url='%s' | bytes=%s",
            full_path,
            relative_url,
            content_len if content_len >= 0 else "stream",
        )
        return relative_url

    async def delete_file(self, file_url: str) -> bool:
        if not file_url:
            return False

        relative_path: Optional[str] = None
        if "/uploads/" in file_url:
            relative_path = file_url.split("/uploads/", 1)[1].strip("/\\")
        elif "storage.googleapis.com/" in file_url:
            # Compatibilidad retroactiva con URLs previas de Google Cloud Storage
            parts = file_url.split("storage.googleapis.com/", 1)[1].strip("/\\").split("/", 1)
            relative_path = parts[1] if len(parts) > 1 else parts[0]
        elif not file_url.startswith("http://") and not file_url.startswith("https://"):
            relative_path = file_url.strip("/\\")

        if not relative_path:
            return False

        full_path = os.path.join(self.base_directory, relative_path)
        return await asyncio.to_thread(_delete_file_from_disk, full_path)

    def get_url(self, file_path_or_url: str, expiration_minutes: int = 60) -> str:
        """En entorno local, normaliza rutas canónicas o URLs a /uploads/<path>."""
        if not file_path_or_url:
            return ""
        clean = file_path_or_url.strip()
        if clean.startswith("/uploads/"):
            return clean
        if clean.startswith("http://") or clean.startswith("https://"):
            if "storage.googleapis.com/" in clean:
                parts = clean.split("storage.googleapis.com/", 1)[1].strip("/\\").split("/", 1)
                rel = parts[1] if len(parts) > 1 else parts[0]
                return f"/uploads/{rel}"
            return clean
        clean_rel = clean.lstrip("/\\")
        return f"/uploads/{clean_rel}"


