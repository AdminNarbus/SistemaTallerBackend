import json
import os
from enum import Enum
from typing import Final, List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES: Final[int] = 60 * 24 * 365 * 100  # 100 años (~52.560.000 minutos, sin límite de expiración práctica)
DEFAULT_MAX_UPLOAD_SIZE_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
DEFAULT_SIGNED_URL_EXPIRATION_MINUTES: Final[int] = 60


class AppEnvironment(str, Enum):
    DEV_LOCAL = "dev_local"
    DEV_LAN = "dev_lan"
    PRODUCTION = "production"


class StorageProviderType(str, Enum):
    LOCAL = "local"
    GCS = "gcs"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Backend Taller Narbus"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Perfil / Entorno de ejecución
    ENVIRONMENT: AppEnvironment = AppEnvironment.DEV_LOCAL

    # Host y Puerto
    HOST: Optional[str] = None
    PORT: int = 8000

    # JWT Security Settings (100 años por defecto para login sin límite)
    SECRET_KEY: str = "narbus_secret_key_taller_2026_super_secure_jwt_token_change_in_prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: Optional[int] = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES

    # PostgreSQL Database Settings
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "taller_narbus"

    DATABASE_URL: Optional[str] = None

    # Storage / Cloud Storage Settings (Bucket Privado con Signed URLs o Local)
    STORAGE_PROVIDER: Union[StorageProviderType, str] = StorageProviderType.LOCAL  # "local" o "gcs"
    UPLOAD_DIR: str = "uploads"  # Ruta local de almacenamiento fallback
    GCS_BUCKET_NAME: Optional[str] = "narbus-taller-media"
    GCS_PROJECT_ID: Optional[str] = None
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = None
    GCS_SIGNED_URL_EXPIRATION_MINUTES: int = DEFAULT_SIGNED_URL_EXPIRATION_MINUTES  # Duración de validez de Signed URLs
    GCS_SERVICE_ACCOUNT_EMAIL: Optional[str] = None  # Service account email para firma de blobs con ADC
    MAX_UPLOAD_SIZE_BYTES: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES

    # URL directa del Frontend (leída desde .env o variable de entorno de Cloud Run)
    FRONTEND_URL: Optional[str] = None

    # CORS Settings (leídas desde BACKEND_CORS_ORIGINS en .env o variables de entorno)
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
    ]

    CORS_ORIGIN_REGEX: Optional[str] = None

    # Restricción perimetral: Solo móviles y origen web autorizado
    ENFORCE_MOBILE_ONLY: bool = False
    ENFORCE_ORIGIN_CHECK: bool = False
    APP_CLIENT_SECRET: Optional[str] = None  # Header opcional X-App-Client-Key para bypass o clientes de confianza

    # Supervisión: Umbrales de permanencia y alertas operacionales (horas configurables)
    # BAJA: 2-4 días | MEDIA: 5-8 días | ALTA: 9-12 días | CRITICA: 13+ días
    SUPERVISION_UMBRAL_TALLER_HORAS_BAJA: int = 48     # 2 días en taller
    SUPERVISION_UMBRAL_TALLER_HORAS_MEDIA: int = 120   # 5 días en taller
    SUPERVISION_UMBRAL_TALLER_HORAS_ALTA: int = 216    # 9 días en taller
    SUPERVISION_UMBRAL_TALLER_HORAS_CRITICA: int = 312  # 13 días en taller
    SUPERVISION_UMBRAL_LIBERADO_HORAS_BAJA: int = 48    # 2 días liberado en ruta
    SUPERVISION_UMBRAL_LIBERADO_HORAS_MEDIA: int = 120  # 5 días liberado en ruta
    SUPERVISION_UMBRAL_LIBERADO_HORAS_ALTA: int = 216   # 9 días liberado en ruta
    SUPERVISION_UMBRAL_LIBERADO_HORAS_CRITICA: int = 312 # 13 días liberado en ruta

    @field_validator("PROJECT_NAME", "VERSION", mode="before")
    @classmethod
    def clean_quoted_strings(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip("\"'").strip()
        return v

    @field_validator("API_V1_STR", mode="before")
    @classmethod
    def clean_api_v1_str(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip("\"'").strip()
            if not v.startswith("/"):
                v = f"/{v}"
        return v

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, set, tuple)):
            return list(v)
        raise ValueError(f"Formato no válido para orígenes CORS: {v}")

    @property
    def server_host(self) -> str:
        if self.HOST:
            return self.HOST
        if self.ENVIRONMENT == AppEnvironment.DEV_LOCAL:
            return "127.0.0.1"
        return "0.0.0.0"

    @property
    def is_reload_enabled(self) -> bool:
        return self.ENVIRONMENT != AppEnvironment.PRODUCTION

    @property
    def effective_cors_origins(self) -> List[str]:
        origins = list(self.BACKEND_CORS_ORIGINS) if isinstance(self.BACKEND_CORS_ORIGINS, (list, tuple, set)) else [self.BACKEND_CORS_ORIGINS]
        if self.FRONTEND_URL and self.FRONTEND_URL.strip():
            clean_url = self.FRONTEND_URL.strip().rstrip("/")
            if clean_url not in origins:
                origins.insert(0, clean_url)
        return origins

    @property
    def effective_cors_origin_regex(self) -> Optional[str]:
        if self.CORS_ORIGIN_REGEX:
            return self.CORS_ORIGIN_REGEX
        if self.ENVIRONMENT in (AppEnvironment.DEV_LAN, AppEnvironment.DEV_LOCAL):
            return r"^(https?://.*|http://.*|capacitor://.*)$"
        # En producción permite por defecto cualquier frontend alojado en Cloud Run o Firebase
        return r"^(https://.*\.run\.app|https://.*\.web\.app|https://.*\.firebaseapp\.com)$"


    @property
    def docs_url(self) -> Optional[str]:
        if self.ENVIRONMENT == AppEnvironment.PRODUCTION:
            return None
        return "/docs"

    @property
    def redoc_url(self) -> Optional[str]:
        if self.ENVIRONMENT == AppEnvironment.PRODUCTION:
            return None
        return "/redoc"

    @property
    def upload_absolute_path(self) -> str:
        return os.path.abspath(self.UPLOAD_DIR)

    @property
    def gcs_public_url_base(self) -> str:
        bucket = self.GCS_BUCKET_NAME or "narbus-taller-media"
        return f"https://storage.googleapis.com/{bucket}"

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql+asyncpg://"):
                url = url.replace("postgresql+asyncpg://", "postgresql://")
            if "ssl=require" in url and "sslmode=require" not in url:
                url = url.replace("ssl=require", "sslmode=require")
            return url
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://")
            # Normalizar para asyncpg: asyncpg utiliza ssl=require y no soporta sslmode ni channel_binding en el query string
            if "sslmode=require" in url:
                url = url.replace("sslmode=require", "ssl=require")
            for cb in ["&channel_binding=require", "?channel_binding=require&", "?channel_binding=require"]:
                url = url.replace(cb, "?" if cb.startswith("?") and cb.endswith("&") else "")
            return url
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()

__all__ = [
    "AppEnvironment",
    "StorageProviderType",
    "Settings",
    "settings",
    "DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES",
    "DEFAULT_MAX_UPLOAD_SIZE_BYTES",
    "DEFAULT_SIGNED_URL_EXPIRATION_MINUTES",
]
