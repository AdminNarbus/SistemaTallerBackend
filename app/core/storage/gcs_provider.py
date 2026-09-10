import asyncio
import logging
import os
from typing import Optional
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError

from app.core.exceptions import BusinessRuleException
from app.core.storage.base import BaseStorageProvider

logger = logging.getLogger(__name__)


def _sync_upload_blob(
    client: storage.Client,
    bucket_name: str,
    blob_name: str,
    file_content: bytes,
    content_type: str,
) -> str:
    """Sube un blob a Google Cloud Storage en un worker thread."""
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(file_content, content_type=content_type)
    
    # URL estándar de acceso público HTTPS en Google Cloud Storage
    public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
    return public_url


def _sync_delete_blob(
    client: storage.Client,
    bucket_name: str,
    blob_name: str,
) -> bool:
    """Elimina un blob de Google Cloud Storage en un worker thread."""
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if blob.exists():
        blob.delete()
        return True
    return False


class GCSStorageProvider(BaseStorageProvider):
    """
    Proveedor de almacenamiento en Google Cloud Storage (GCS).
    
    - En Local: Soporta autenticación mediante archivo de Service Account JSON
      (configurado en GOOGLE_APPLICATION_CREDENTIALS o en .env).
    - En Producción (Google Cloud Run / Compute Engine / GKE):
      Utiliza de forma transparente las Application Default Credentials (ADC)
      inyectadas por la plataforma de Google Cloud sin requerir archivos de clave.
    """

    def __init__(
        self,
        bucket_name: str,
        project_id: Optional[str] = None,
        credentials_file: Optional[str] = None,
    ):
        if not bucket_name:
            raise ValueError("Se requiere configurar GCS_BUCKET_NAME para el proveedor 'gcs'.")

        self.bucket_name = bucket_name
        self.project_id = project_id
        self.credentials_file = credentials_file

        # Inicialización del cliente de Google Cloud Storage
        try:
            if credentials_file and os.path.exists(credentials_file):
                logger.info(
                    "[STORAGE_GCS] Inicializando cliente con archivo de credenciales: '%s'",
                    credentials_file,
                )
                self.client = storage.Client.from_service_account_json(
                    credentials_file, project=project_id
                )
            else:
                logger.info(
                    "[STORAGE_GCS] Inicializando cliente con Application Default Credentials (ADC)..."
                )
                self.client = storage.Client(project=project_id)
        except Exception as e:
            logger.error(
                "[STORAGE_GCS] Error al inicializar cliente de Google Cloud Storage: %s",
                e,
                exc_info=True,
            )
            raise BusinessRuleException(
                f"No fue posible autenticar con Google Cloud Storage: {str(e)}"
            )

    async def upload_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        folder: str = "evidencias",
    ) -> str:
        folder_clean = folder.strip("/\\")
        blob_name = f"{folder_clean}/{filename}" if folder_clean else filename

        try:
            public_url = await asyncio.to_thread(
                _sync_upload_blob,
                self.client,
                self.bucket_name,
                blob_name,
                file_content,
                content_type,
            )
            logger.info(
                "[STORAGE_GCS] Archivo subido exitosamente a GCS | bucket='%s' | blob='%s' | bytes=%d | url='%s'",
                self.bucket_name,
                blob_name,
                len(file_content),
                public_url,
            )
            return public_url
        except GoogleCloudError as gce:
            logger.error(
                "[STORAGE_GCS] Error de Google Cloud Storage al subir archivo '%s': %s",
                blob_name,
                gce,
                exc_info=True,
            )
            raise BusinessRuleException(
                f"Fallo al almacenar la imagen en Google Cloud Storage: {str(gce)}"
            )
        except Exception as e:
            logger.error(
                "[STORAGE_GCS] Error inesperado al subir archivo '%s': %s",
                blob_name,
                e,
                exc_info=True,
            )
            raise BusinessRuleException(
                f"Error inesperado durante la subida a Cloud Storage: {str(e)}"
            )

    async def delete_file(self, file_url: str) -> bool:
        """Extrae el blob_name desde la URL de GCS y lo elimina."""
        expected_prefix = f"https://storage.googleapis.com/{self.bucket_name}/"
        if not file_url.startswith(expected_prefix):
            return False

        blob_name = file_url.replace(expected_prefix, "").strip("/")
        try:
            return await asyncio.to_thread(
                _sync_delete_blob,
                self.client,
                self.bucket_name,
                blob_name,
            )
        except Exception as e:
            logger.warning(
                "[STORAGE_GCS] No se pudo eliminar el archivo '%s' en GCS: %s",
                blob_name,
                e,
            )
            return False
