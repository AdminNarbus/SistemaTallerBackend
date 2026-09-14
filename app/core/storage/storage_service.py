import logging
import os
import uuid
from typing import Final, Optional, Set
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import BusinessRuleException
from app.core.storage.base import BaseStorageProvider
from app.core.storage.dtos import StorageUploadResultDTO
from app.core.storage.gcs_provider import GCSStorageProvider
from app.core.storage.local_provider import LocalStorageProvider

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXTENSIONS: Final[Set[str]] = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_MIME_TYPES: Final[Set[str]] = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/octet-stream",  # Algunos clientes envían octet-stream para fotos móviles
}


def _validate_image_file(file: Optional[UploadFile], content: bytes) -> str:
    """Valida precondiciones de archivo e integridad de contenido (Fail-Fast)."""
    if not file or not file.filename:
        raise BusinessRuleException("No se proporcionó ningún archivo para subir.")

    extension = (os.path.splitext(file.filename)[1] or ".jpg").lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise BusinessRuleException(
            f"Tipo de archivo no permitido: '{extension}'. Formatos válidos: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}"
        )

    content_type = file.content_type or "image/jpeg"
    if content_type not in ALLOWED_IMAGE_MIME_TYPES:
        logger.warning(
            "[STORAGE_SERVICE] Advertencia: Content-Type no estándar '%s' para archivo '%s'",
            content_type,
            file.filename,
        )

    tamano_bytes = len(content)
    if tamano_bytes == 0:
        raise BusinessRuleException("El archivo subido está vacío (0 bytes).")

    max_bytes = settings.MAX_UPLOAD_SIZE_BYTES
    if tamano_bytes > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        raise BusinessRuleException(
            f"El archivo supera el tamaño máximo permitido de {max_mb} MB (tamaño recibido: {tamano_bytes / (1024*1024):.2f} MB)."
        )

    return extension


class StorageService:
    """
    Servicio centralizado de almacenamiento de archivos.
    Valida formatos, extensiones y tamaños máximos permitidos,
    y orquesta el proveedor activo (Google Cloud Storage o Disco Local).
    """

    def __init__(self, provider: Optional[BaseStorageProvider] = None):
        self._provider = provider

    @property
    def provider(self) -> BaseStorageProvider:
        """Inicialización diferida (lazy) del proveedor según la configuración."""
        if self._provider is None:
            provider_type = (settings.STORAGE_PROVIDER or "local").lower().strip()

            if provider_type == "gcs":
                try:
                    logger.info(
                        "[STORAGE_SERVICE] Configurando proveedor Google Cloud Storage (Bucket: '%s')",
                        settings.GCS_BUCKET_NAME,
                    )
                    self._provider = GCSStorageProvider(
                        bucket_name=settings.GCS_BUCKET_NAME or "narbus-taller-media",
                        project_id=settings.GCS_PROJECT_ID,
                        credentials_file=settings.GOOGLE_APPLICATION_CREDENTIALS,
                    )
                except Exception as e:
                    logger.error(
                        "[STORAGE_SERVICE] No se pudo inicializar GCSStorageProvider (%s). "
                        "Revirtiendo a LocalStorageProvider para evitar caída del servicio.",
                        e,
                    )
                    self._provider = LocalStorageProvider()
            else:
                logger.info(
                    "[STORAGE_SERVICE] Usando LocalStorageProvider (directorio: '%s')",
                    getattr(settings, "UPLOAD_DIR", "uploads"),
                )
                self._provider = LocalStorageProvider()

        return self._provider

    async def upload_image(
        self,
        file: UploadFile,
        folder: str = "evidencias",
    ) -> StorageUploadResultDTO:
        """
        Valida y sube una imagen al almacenamiento configurado.

        Args:
            file: Instancia de FastAPI UploadFile.
            folder: Carpeta o prefijo destino (ej. 'evidencias', 'solicitudes', 'neumaticos').

        Returns:
            StorageUploadResultDTO con metadatos y URL accesible.
        """
        content = await file.read() if file else b""
        extension = _validate_image_file(file, content)
        unique_filename = f"{uuid.uuid4()}{extension}"
        content_type = file.content_type or "image/jpeg"

        stored_path = await self.provider.upload_file(
            file_content=content,
            filename=unique_filename,
            content_type=content_type,
            folder=folder,
        )
        accessible_url = self.provider.get_url(stored_path)

        return StorageUploadResultDTO(
            url=accessible_url,
            path=stored_path,
            filename=unique_filename,
            original_filename=file.filename or unique_filename,
            size_bytes=len(content),
            content_type=content_type,
        )

    def get_url(
        self,
        file_path_or_url: Optional[str],
        expiration_minutes: Optional[int] = None,
    ) -> Optional[str]:
        """
        Genera la URL lista para ser consumida por el cliente frontend:
        - En GCS: Genera una Signed URL v4 con validez temporal (60 min).
        - En Local: Retorna la ruta relativa estándar /uploads/...
        """
        if not file_path_or_url:
            return None
        return self.provider.get_url(file_path_or_url, expiration_minutes=expiration_minutes)

    async def delete_file(self, file_url: str) -> bool:
        """Elimina un archivo a partir de su URL o path canónico."""
        if not file_url:
            return False
        return await self.provider.delete_file(file_url)


# Instancia singleton accesible globalmente
storage_service = StorageService()

__all__ = [
    "StorageService",
    "storage_service",
    "ALLOWED_IMAGE_EXTENSIONS",
    "ALLOWED_IMAGE_MIME_TYPES",
]
