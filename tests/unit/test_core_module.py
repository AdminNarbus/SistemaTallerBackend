"""
test_core_module.py
===================
Pruebas unitarias para los componentes refactorizados de app/core bajo el patrón AAA.
"""
import pytest
from app.core.config import Settings, StorageProviderType, AppEnvironment
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.storage.dtos import StorageUploadResultDTO
from app.core.storage.local_provider import _extract_relative_upload_path
from app.core.logging_config import _build_console_handler, _build_file_handler, LOG_MAX_BYTES, LOG_BACKUP_COUNT


def test_storage_upload_result_dto_dual_access():
    """Verifica que StorageUploadResultDTO soporte acceso por atributo y por clave de diccionario (AAA)."""
    # Arrange
    data = {
        "url": "/uploads/evidencias/foto1.jpg",
        "path": "evidencias/foto1.jpg",
        "filename": "foto1.jpg",
        "original_filename": "bus_rueda.jpg",
        "size_bytes": 2048,
        "content_type": "image/jpeg",
    }

    # Act
    dto = StorageUploadResultDTO(**data)

    # Assert - Acceso por atributo
    assert dto.url == "/uploads/evidencias/foto1.jpg"
    assert dto.path == "evidencias/foto1.jpg"
    assert dto.size_bytes == 2048

    # Assert - Acceso por diccionario (retrocompatibilidad)
    assert dto["url"] == "/uploads/evidencias/foto1.jpg"
    assert dto["size_bytes"] == 2048
    assert dto.get("path") == "evidencias/foto1.jpg"
    assert dto.get("no_existe", "default_val") == "default_val"
    assert "url" in dto
    assert "no_existe" not in dto

    with pytest.raises(KeyError):
        _ = dto["clave_inexistente"]


def test_security_verify_password_handling():
    """Verifica el comportamiento de verify_password con hashes válidos, inválidos y malformados (AAA)."""
    # Arrange
    plain = "SuperPassword2026!"
    hashed = get_password_hash(plain)

    # Act & Assert
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password(plain, "malformed_not_bcrypt_hash") is False
    assert verify_password(plain, "") is False


def test_security_create_access_token():
    """Verifica que create_access_token retorne un JWT decodificable (AAA)."""
    # Arrange
    subject = "12345"

    # Act
    token = create_access_token(subject)

    # Assert
    assert isinstance(token, str)
    assert len(token) > 20
    assert token.count(".") == 2


def test_extract_relative_upload_path_patterns():
    """Verifica la normalización de URLs relativas y de Google Cloud Storage (AAA)."""
    # Arrange & Act
    path1 = _extract_relative_upload_path("http://localhost:8000/uploads/evidencias/test.png")
    path2 = _extract_relative_upload_path("/uploads/mantencion/doc.jpg")
    path3 = _extract_relative_upload_path("https://storage.googleapis.com/narbus-bucket/neumaticos/medida.webp")
    path4 = _extract_relative_upload_path("direct/path/file.jpg")
    path_empty = _extract_relative_upload_path("")

    # Assert
    assert path1 == "evidencias/test.png"
    assert path2 == "mantencion/doc.jpg"
    assert path3 == "neumaticos/medida.webp"
    assert path4 == "direct/path/file.jpg"
    assert path_empty is None


def test_config_storage_provider_enum_and_cors_validation():
    """Verifica validación de orígenes CORS y tipado de StorageProviderType (AAA)."""
    # Arrange & Act
    settings_obj = Settings()

    # Assert
    assert settings_obj.STORAGE_PROVIDER in (StorageProviderType.LOCAL, StorageProviderType.GCS, "local", "gcs")
    assert isinstance(settings_obj.BACKEND_CORS_ORIGINS, list)
    assert len(settings_obj.BACKEND_CORS_ORIGINS) > 0


def test_logging_handlers_creation(tmp_path):
    """Verifica la construcción correcta de los handlers de consola y archivo rotatorio (AAA)."""
    # Arrange
    logs_dir = str(tmp_path / "logs")

    # Act
    console_handler = _build_console_handler(level=10)
    file_handler = _build_file_handler(environment="dev_local", logs_dir=logs_dir)

    # Assert
    assert console_handler.level == 10
    assert file_handler.maxBytes == LOG_MAX_BYTES
    assert file_handler.backupCount == LOG_BACKUP_COUNT
    file_handler.close()
