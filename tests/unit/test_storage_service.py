import io
import pytest
from unittest.mock import MagicMock, patch
from fastapi import UploadFile

from app.core.exceptions import BusinessRuleException
from app.core.storage.base import BaseStorageProvider
from app.core.storage.gcs_provider import GCSStorageProvider
from app.core.storage.local_provider import LocalStorageProvider
from app.core.storage.storage_service import StorageService


@pytest.fixture
def dummy_image_file():
    """Genera un archivo UploadFile de prueba con contenido JPG válido."""
    content = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00" + b"A" * 1024
    file_obj = io.BytesIO(content)
    return UploadFile(file=file_obj, filename="foto_bus_101.jpg", headers={"content-type": "image/jpeg"})


@pytest.mark.asyncio
async def test_upload_image_no_file():
    service = StorageService(provider=MagicMock(spec=BaseStorageProvider))
    with pytest.raises(BusinessRuleException, match="No se proporcionó ningún archivo"):
        await service.upload_image(file=None)


@pytest.mark.asyncio
async def test_upload_image_invalid_extension():
    service = StorageService(provider=MagicMock(spec=BaseStorageProvider))
    invalid_file = UploadFile(file=io.BytesIO(b"contenido"), filename="documento.pdf")
    with pytest.raises(BusinessRuleException, match="Tipo de archivo no permitido"):
        await service.upload_image(file=invalid_file)


@pytest.mark.asyncio
async def test_upload_image_empty_file():
    service = StorageService(provider=MagicMock(spec=BaseStorageProvider))
    empty_file = UploadFile(file=io.BytesIO(b""), filename="vacio.png")
    with pytest.raises(BusinessRuleException, match="está vacío"):
        await service.upload_image(file=empty_file)


@pytest.mark.asyncio
async def test_upload_image_oversized():
    service = StorageService(provider=MagicMock(spec=BaseStorageProvider))
    # 11 MB > 10 MB límite
    large_content = b"X" * (11 * 1024 * 1024)
    large_file = UploadFile(file=io.BytesIO(large_content), filename="pesado.jpg")
    with pytest.raises(BusinessRuleException, match="supera el tamaño máximo permitido"):
        await service.upload_image(file=large_file)


@pytest.mark.asyncio
async def test_upload_image_local_provider(tmp_path, dummy_image_file):
    """Verifica que el proveedor local guarda el archivo y genera una URL relativa /uploads/..."""
    local_provider = LocalStorageProvider(base_directory=str(tmp_path))
    service = StorageService(provider=local_provider)

    result = await service.upload_image(file=dummy_image_file, folder="evidencias")

    assert "url" in result
    assert result["url"].startswith("/uploads/evidencias/")
    assert result["original_filename"] == "foto_bus_101.jpg"
    assert result["size_bytes"] > 0
    assert result["content_type"] == "image/jpeg"

    # Verificar existencia en disco
    filename = result["filename"]
    saved_path = tmp_path / "evidencias" / filename
    assert saved_path.exists()

    # Probar borrado
    deleted = await service.delete_file(result["url"])
    assert deleted is True
    assert not saved_path.exists()


@pytest.mark.asyncio
async def test_upload_image_gcs_provider_mock(dummy_image_file):
    """Verifica la subida con el proveedor de Google Cloud Storage usando un mock de la SDK."""
    with patch("google.cloud.storage.Client") as mock_storage_client_cls:
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = (
            "https://storage.googleapis.com/narbus-taller-media/neumaticos/signed.jpg?X-Goog-Signature=123"
        )

        mock_storage_client_cls.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        gcs_provider = GCSStorageProvider(bucket_name="narbus-taller-media", project_id="narbus-prod")
        service = StorageService(provider=gcs_provider)

        result = await service.upload_image(file=dummy_image_file, folder="neumaticos")

        assert result["url"].startswith("https://storage.googleapis.com/narbus-taller-media/neumaticos/")
        assert "X-Goog-Signature" in result["url"]
        assert result["path"].startswith("neumaticos/")
        assert result["original_filename"] == "foto_bus_101.jpg"

        # Verificar llamadas al SDK de GCP
        mock_client.bucket.assert_called_with("narbus-taller-media")
        assert mock_bucket.blob.call_count >= 1
        mock_blob.upload_from_string.assert_called_once()
        mock_blob.generate_signed_url.assert_called_once()


@pytest.mark.asyncio
async def test_upload_image_solicitudes_folder(tmp_path, dummy_image_file):
    """Verifica la subida de imágenes a la carpeta 'solicitudes' tal como requiere el flujo de conductores."""
    local_provider = LocalStorageProvider(base_directory=str(tmp_path))
    service = StorageService(provider=local_provider)

    result = await service.upload_image(file=dummy_image_file, folder="solicitudes")

    assert result["url"].startswith("/uploads/solicitudes/")
    assert result["url"].endswith(".jpg")
    
    filename = result["filename"]
    saved_path = tmp_path / "solicitudes" / filename
    assert saved_path.exists()


@pytest.mark.asyncio
async def test_delete_file_legacy_gcs_url(tmp_path):
    """Verifica que delete_file elimine el archivo físico incluso si se recibe una URL antigua de GCS."""
    local_provider = LocalStorageProvider(base_directory=str(tmp_path))
    service = StorageService(provider=local_provider)

    # Crear archivo simulado en el directorio local montado
    target_dir = tmp_path / "solicitudes"
    target_dir.mkdir(parents=True, exist_ok=True)
    test_file = target_dir / "foto_legacy_123.jpg"
    test_file.write_bytes(b"contenido_de_prueba")
    assert test_file.exists()

    # URL antigua de GCS
    legacy_url = "https://storage.googleapis.com/narbus-taller-media/solicitudes/foto_legacy_123.jpg"
    deleted = await service.delete_file(legacy_url)

    assert deleted is True
    assert not test_file.exists()


def test_get_url_local_provider(tmp_path):
    """Verifica la resolución de URLs en el proveedor local con rutas relativas y legacy URLs."""
    local_provider = LocalStorageProvider(base_directory=str(tmp_path))
    service = StorageService(provider=local_provider)

    # Caso 1: Ruta canónica relativa
    assert service.get_url("solicitudes/foto1.jpg") == "/uploads/solicitudes/foto1.jpg"

    # Caso 2: Ruta ya formateada con /uploads/
    assert service.get_url("/uploads/solicitudes/foto2.jpg") == "/uploads/solicitudes/foto2.jpg"

    # Caso 3: URL antigua de Google Cloud Storage
    legacy_gcs = "https://storage.googleapis.com/mi-bucket/solicitudes/foto3.jpg"
    assert service.get_url(legacy_gcs) == "/uploads/solicitudes/foto3.jpg"

    # Caso 4: None o vacío retorna None
    assert service.get_url(None) is None
    assert service.get_url("") is None


def test_get_url_gcs_provider_and_cache():
    """Verifica la generación de Signed URLs v4 y el funcionamiento de la memoria caché TTL."""
    with patch("google.cloud.storage.Client") as mock_storage_client_cls:
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = (
            "https://storage.googleapis.com/narbus-taller-media/solicitudes/test.jpg?X-Goog-Signature=abc"
        )

        mock_storage_client_cls.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        gcs_provider = GCSStorageProvider(bucket_name="narbus-taller-media", project_id="narbus-prod")
        service = StorageService(provider=gcs_provider)

        # 1. Primera llamada: debe invocar generate_signed_url
        url1 = service.get_url("solicitudes/test.jpg", expiration_minutes=60)
        assert "X-Goog-Signature=abc" in url1
        assert mock_blob.generate_signed_url.call_count == 1

        # 2. Segunda llamada con la misma ruta: debe responder desde la caché interna
        url2 = service.get_url("solicitudes/test.jpg", expiration_minutes=60)
        assert url2 == url1
        assert mock_blob.generate_signed_url.call_count == 1  # No se incrementó

        # 3. Llamada con URL legada de GCS: debe extraer la ruta del blob y reutilizar la caché
        legacy_url = "https://storage.googleapis.com/narbus-taller-media/solicitudes/test.jpg"
        url3 = service.get_url(legacy_url, expiration_minutes=60)
        assert url3 == url1
        assert mock_blob.generate_signed_url.call_count == 1


def test_resolve_service_account_email():
    """Verifica la resolución del email de Service Account para firma de URLs en Cloud Run."""
    from app.core.storage.gcs_provider import _resolve_service_account_email
    from app.core.config import settings

    # Caso 1: Vía settings
    original = settings.GCS_SERVICE_ACCOUNT_EMAIL
    try:
        settings.GCS_SERVICE_ACCOUNT_EMAIL = "custom-sa@project.iam.gserviceaccount.com"
        assert _resolve_service_account_email(None) == "custom-sa@project.iam.gserviceaccount.com"
    finally:
        settings.GCS_SERVICE_ACCOUNT_EMAIL = original

    # Caso 2: Vía credentials object
    mock_cred = MagicMock()
    mock_cred.service_account_email = "sa-cred@developer.gserviceaccount.com"
    assert _resolve_service_account_email(mock_cred) == "sa-cred@developer.gserviceaccount.com"

    # Caso 3: Vía metadata server mock
    mock_cred_default = MagicMock()
    mock_cred_default.service_account_email = "default"
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b"dummy-service-account@developer.gserviceaccount.com\n"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        email = _resolve_service_account_email(mock_cred_default)
        assert email == "dummy-service-account@developer.gserviceaccount.com"


