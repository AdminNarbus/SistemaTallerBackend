import asyncio
import datetime
import json
import logging
import os
import time
import urllib.request
from typing import BinaryIO, Dict, Optional, Tuple, Union
from google.auth.credentials import Signing
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError

from app.core.config import settings
from app.core.exceptions import BusinessRuleException
from app.core.storage.base import BaseStorageProvider

logger = logging.getLogger(__name__)

# Caché en memoria para Signed URLs: blob_name -> (expires_timestamp, signed_url)
_SIGNED_URL_CACHE: Dict[str, Tuple[float, str]] = {}


def _sync_upload_blob(
    client: storage.Client,
    bucket_name: str,
    blob_name: str,
    file_content: Union[bytes, BinaryIO],
    content_type: str,
) -> str:
    """Sube un blob al bucket privado de Google Cloud Storage en un worker thread."""
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if isinstance(file_content, bytes):
        blob.upload_from_string(file_content, content_type=content_type)
    else:
        blob.upload_from_file(file_content, content_type=content_type)
    return blob_name


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


def _resolve_service_account_email(credentials) -> Optional[str]:
    """
    Resuelve la dirección de correo de la Service Account utilizada por el proceso.
    Prioridad:
    1. Variable explícita GCS_SERVICE_ACCOUNT_EMAIL configurada en settings / entorno.
    2. Atributo service_account_email de credentials (si no es 'default' y contiene '@').
    3. Servidor de metadatos interno de Google Cloud (Cloud Run / Compute Engine).
    """
    configured_email = getattr(settings, "GCS_SERVICE_ACCOUNT_EMAIL", None)
    if configured_email:
        return configured_email

    cred_email = getattr(credentials, "service_account_email", None)
    if cred_email and cred_email != "default" and "@" in str(cred_email):
        return cred_email

    # Consultar el servidor de metadatos interno de Cloud Run
    try:
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            meta_email = resp.read().decode("utf-8").strip()
            if meta_email and "@" in meta_email:
                logger.info("[STORAGE_GCS] Service Account email resuelto desde metadata server: '%s'", meta_email)
                return meta_email
    except Exception as me:
        logger.debug("[STORAGE_GCS] No se pudo consultar metadata server de GCP: %s", me)

    return cred_email


def _get_iam_access_token(credentials) -> Optional[str]:
    """
    Obtiene un access token OAuth2 que incluya el scope necesario para llamar a la API
    de IAM Credentials (IAM signBlob) desde Cloud Run: 'https://www.googleapis.com/auth/cloud-platform'.
    Si el token por defecto sólo tiene scopes de Cloud Storage ('devstorage.*'),
    la API de IAM rechaza la firma con error ACCESS_TOKEN_SCOPE_INSUFFICIENT.
    """
    # 1. Intentar consultar directamente el metadata server de Cloud Run con el scope cloud-platform
    try:
        url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token?scopes=https://www.googleapis.com/auth/cloud-platform"
        req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            token = data.get("access_token")
            if token:
                logger.debug("[STORAGE_GCS] Token con scope 'cloud-platform' obtenido desde metadata server.")
                return token
    except Exception as me:
        logger.debug("[STORAGE_GCS] No se pudo obtener token con scope desde metadata server: %s", me)

    # 2. Si credentials es de Compute Engine / ADC, configurar scopes antes de refrescar
    if hasattr(credentials, "_scopes"):
        credentials._scopes = ["https://www.googleapis.com/auth/cloud-platform"]

    from google.auth.transport import requests as auth_requests
    auth_req = auth_requests.Request()
    if not hasattr(credentials, "valid") or not credentials.valid:
        credentials.refresh(auth_req)

    return getattr(credentials, "token", None)


def _sync_generate_signed_url(
    client: storage.Client,
    bucket_name: str,
    blob_name: str,
    expiration_minutes: int = 60,
) -> str:
    """
    Genera una Signed URL v4 para acceso seguro temporal a un blob privado.
    Compatible tanto con Service Account JSON (desarrollo/claves con Signing)
    como con Application Default Credentials en Cloud Run (IAM signBlob).
    """
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    expires_delta = datetime.timedelta(minutes=expiration_minutes)
    credentials = client._credentials

    # Caso 1: Credenciales con clave privada local (Service Account JSON implementa Signing)
    if isinstance(credentials, Signing):
        return blob.generate_signed_url(
            version="v4",
            expiration=expires_delta,
            method="GET",
        )

    # Caso 2: Cloud Run / ADC sin clave privada local.
    # Obtener token con scope requerido para IAM signBlob ('cloud-platform')
    token = _get_iam_access_token(credentials)
    sa_email = _resolve_service_account_email(credentials)

    return blob.generate_signed_url(
        version="v4",
        expiration=expires_delta,
        method="GET",
        service_account_email=sa_email,
        access_token=token,
    )


class GCSStorageProvider(BaseStorageProvider):
    """
    Proveedor de almacenamiento en Google Cloud Storage (GCS) con Bucket 100% Privado y Signed URLs.
    
    - Al subir: Almacena en el bucket privado y retorna el path canónico (ej: 'solicitudes/uuid.jpg').
    - Al consultar: Genera Signed URLs v4 con expiración temporal (default 60 min).
    - Caching: Reutiliza URLs firmadas vigentes en memoria evitando llamadas redundantes de firma.
    """

    def __init__(
        self,
        bucket_name: str,
        project_id: Optional[str] = None,
        credentials_file: Optional[str] = None,
        expiration_minutes: Optional[int] = None,
    ):
        if not bucket_name:
            raise ValueError("Se requiere configurar GCS_BUCKET_NAME para el proveedor 'gcs'.")

        self.bucket_name = bucket_name
        self.project_id = project_id
        self.credentials_file = credentials_file
        self.expiration_minutes = expiration_minutes or getattr(settings, "GCS_SIGNED_URL_EXPIRATION_MINUTES", 60)

        # Inicialización del cliente de Google Cloud Storage
        try:
            from google.api_core.client_options import ClientOptions
            gcs_scopes = [
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/devstorage.full_control",
            ]
            client_options = ClientOptions(scopes=gcs_scopes)

            if credentials_file and os.path.exists(credentials_file):
                logger.info(
                    "[STORAGE_GCS] Inicializando cliente con archivo de credenciales: '%s'",
                    credentials_file,
                )
                self.client = storage.Client.from_service_account_json(
                    credentials_file, project=project_id, client_options=client_options
                )
            else:
                logger.info(
                    "[STORAGE_GCS] Inicializando cliente con Application Default Credentials (ADC)..."
                )
                self.client = storage.Client(project=project_id, client_options=client_options)
        except Exception as e:
            logger.error(
                "[STORAGE_GCS] Error al inicializar cliente de Google Cloud Storage: %s",
                e,
                exc_info=True,
            )
            raise BusinessRuleException(
                f"No fue posible autenticar con Google Cloud Storage: {str(e)}"
            )

    def _normalize_blob_name(self, file_path_or_url: str) -> str:
        """Extrae el path limpio dentro del bucket eliminando esquemas y parámetros."""
        if not file_path_or_url:
            return ""
        clean = file_path_or_url.strip().split("?")[0]
        prefix_with_bucket = f"storage.googleapis.com/{self.bucket_name}/"
        if prefix_with_bucket in clean:
            clean = clean.split(prefix_with_bucket, 1)[1]
        elif "storage.googleapis.com/" in clean:
            parts = clean.split("storage.googleapis.com/", 1)[1].split("/", 1)
            clean = parts[1] if len(parts) > 1 else parts[0]
        elif clean.startswith("/uploads/"):
            clean = clean.replace("/uploads/", "", 1)
        elif clean.startswith("uploads/"):
            clean = clean.replace("uploads/", "", 1)
        return clean.strip("/\\")

    async def upload_file(
        self,
        file_content: Union[bytes, BinaryIO],
        filename: str,
        content_type: str,
        folder: str = "evidencias",
    ) -> str:
        folder_clean = folder.strip("/\\")
        blob_name = f"{folder_clean}/{filename}" if folder_clean else filename

        try:
            await asyncio.to_thread(
                _sync_upload_blob,
                self.client,
                self.bucket_name,
                blob_name,
                file_content,
                content_type,
            )
            content_len = len(file_content) if isinstance(file_content, bytes) else -1
            logger.info(
                "[STORAGE_GCS] Archivo subido exitosamente a GCS privado | bucket='%s' | blob='%s' | bytes=%s",
                self.bucket_name,
                blob_name,
                content_len if content_len >= 0 else "stream",
            )
            return blob_name
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

    def get_url(self, file_path_or_url: str, expiration_minutes: Optional[int] = None) -> str:
        """
        Genera una Signed URL v4 con validez temporal para un blob privado en GCS.
        Reutiliza la URL si aún está vigente en caché para evitar sobrecoste de firma.
        """
        blob_name = self._normalize_blob_name(file_path_or_url)
        if not blob_name:
            return ""

        exp_minutes = expiration_minutes or self.expiration_minutes
        now = time.time()

        # Verificar si existe en caché con al menos 5 minutos de holgura
        cached = _SIGNED_URL_CACHE.get(blob_name)
        if cached:
            expires_at, signed_url = cached
            if now < (expires_at - 300):
                return signed_url

        try:
            signed_url = _sync_generate_signed_url(
                self.client,
                self.bucket_name,
                blob_name,
                expiration_minutes=exp_minutes,
            )
            # Almacenar en caché
            cache_ttl = exp_minutes * 60
            _SIGNED_URL_CACHE[blob_name] = (now + cache_ttl, signed_url)
            return signed_url
        except Exception as e:
            logger.error(
                "[STORAGE_GCS] No se pudo generar Signed URL para '%s': %s. Retornando URL estándar.",
                blob_name,
                e,
                exc_info=True,
            )
            return f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"

    async def delete_file(self, file_url: str) -> bool:
        """Extrae el blob_name y lo elimina del bucket de GCS."""
        blob_name = self._normalize_blob_name(file_url)
        if not blob_name:
            return False

        # Invalida de caché si estuviera almacenado
        _SIGNED_URL_CACHE.pop(blob_name, None)

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

