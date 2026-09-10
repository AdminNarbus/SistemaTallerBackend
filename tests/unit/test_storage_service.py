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

        mock_storage_client_cls.return_value = mock_client
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        gcs_provider = GCSStorageProvider(bucket_name="narbus-taller-media", project_id="narbus-prod")
        service = StorageService(provider=gcs_provider)

        result = await service.upload_image(file=dummy_image_file, folder="neumaticos")

        assert result["url"].startswith("https://storage.googleapis.com/narbus-taller-media/neumaticos/")
        assert result["original_filename"] == "foto_bus_101.jpg"

        # Verificar llamadas al SDK de GCP
        mock_client.bucket.assert_called_with("narbus-taller-media")
        mock_bucket.blob.assert_called_once()
        mock_blob.upload_from_string.assert_called_once()
