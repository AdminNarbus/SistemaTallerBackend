import json
import os
import re
from enum import Enum
from typing import Final, List, Literal, Optional, Union

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES: Final[int] = 30
DEFAULT_REFRESH_TOKEN_EXPIRE_MINUTES: Final[int] = 60 * 24 * 30
DEFAULT_MAX_UPLOAD_SIZE_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_VIDEO_UPLOAD_SIZE_BYTES: Final[Optional[int]] = None
DEFAULT_MAX_VIDEO_WIDTH: Final[int] = 1280
DEFAULT_MAX_VIDEO_HEIGHT: Final[int] = 720
DEFAULT_MAX_VIDEO_FPS: Final[Optional[int]] = None
DEFAULT_MAX_VIDEO_DURATION_SECONDS: Final[Optional[int]] = None
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
    SEED_ON_STARTUP: bool = True

    CONDUCTORES_SYNC_URL: str = "https://backendnarbus-100590754321.us-east4.run.app/api/v1/publico/conductores"
    CONDUCTORES_SYNC_SECRET: Optional[SecretStr] = None
    CONDUCTORES_SYNC_TIMER_ENABLED: bool = True

    # Alertas por Meta WhatsApp Cloud API; activación explícita por entorno.
    WHATSAPP_ENABLED: bool = False
    WHATSAPP_TIMER_ENABLED: bool = True
    WHATSAPP_ACCESS_TOKEN: Optional[SecretStr] = None
    WHATSAPP_PHONE_NUMBER_ID: str = Field(default="", pattern=r"^[0-9]*$")
    WHATSAPP_API_VERSION: str = Field(default="", pattern=r"^(v[0-9]+\.[0-9]+)?$")
    WHATSAPP_TEMPLATE_NAME: str = Field(default="alerta_taller_visual", pattern=r"^[a-z0-9_]+$")
    WHATSAPP_TEMPLATE_LANGUAGE: str = Field(default="es", pattern=r"^[a-z]{2,3}(_[A-Z]{2})?$")
    WHATSAPP_DESTINATARIOS: str = ""
    WHATSAPP_SEVERIDAD_MINIMA: Literal["BAJA", "MEDIA", "ALTA", "CRITICA"] = "BAJA"
    WHATSAPP_INTERVAL_SECONDS: int = Field(default=300, ge=60, le=86400)
    WHATSAPP_TIMEOUT_SECONDS: int = Field(default=20, ge=1, le=60)
    WHATSAPP_SOLICITUDES_ENABLED: bool = False
    WHATSAPP_SOLICITUDES_DESTINATARIOS: str = ""
    WHATSAPP_SOLICITUDES_TEMPLATE_NAME: str = Field(default="narbus_reporte_fallas_visual", pattern=r"^[a-z0-9_]+$")
    WHATSAPP_SOLICITUDES_TEMPLATE_LANGUAGE: str = Field(default="es_CL", pattern=r"^[a-z]{2,3}(_[A-Z]{2})?$")
    WHATSAPP_SOLICITUDES_INTERVAL_SECONDS: int = Field(default=15, ge=5, le=3600)

    TELEGRAM_ENABLED: bool = False
    TELEGRAM_TIMER_ENABLED: bool = True
    TELEGRAM_SOLICITUDES_ENABLED: bool = False
    TELEGRAM_BOT_TOKEN: Optional[SecretStr] = None
    TELEGRAM_DESTINATARIOS: str = ""
    TELEGRAM_SOLICITUDES_DESTINATARIOS: str = ""
    TELEGRAM_SEVERIDAD_MINIMA: Literal["BAJA", "MEDIA", "ALTA", "CRITICA"] = "BAJA"
    TELEGRAM_INTERVAL_SECONDS: int = Field(default=300, ge=60, le=86400)
    TELEGRAM_SOLICITUDES_INTERVAL_SECONDS: int = Field(default=15, ge=5, le=3600)
    TELEGRAM_TIMEOUT_SECONDS: int = Field(default=20, ge=1, le=60)

    @field_validator("TELEGRAM_DESTINATARIOS", "TELEGRAM_SOLICITUDES_DESTINATARIOS")
    @classmethod
    def validar_chats_telegram(cls, value: str) -> str:
        chats = list(dict.fromkeys(x.strip() for x in value.split(",") if x.strip()))
        if len(chats) > 20 or any(not re.fullmatch(r"-?[1-9][0-9]{0,19}", x) for x in chats):
            raise ValueError("Configure hasta 20 identificadores numéricos de chat de Telegram")
        return ",".join(chats)

    @model_validator(mode="after")
    def validar_telegram(self) -> "Settings":
        token = self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_BOT_TOKEN.get_secret_value().strip()
        if self.TELEGRAM_ENABLED and not (token and self.TELEGRAM_DESTINATARIOS):
            raise ValueError("Telegram requiere token y chats de alertas")
        if self.TELEGRAM_SOLICITUDES_ENABLED and not (token and self.TELEGRAM_SOLICITUDES_DESTINATARIOS):
            raise ValueError("Telegram requiere token y chats de solicitudes")
        return self

    @field_validator("WHATSAPP_DESTINATARIOS", "WHATSAPP_SOLICITUDES_DESTINATARIOS")
    @classmethod
    def validar_destinatarios_whatsapp(cls, value: str) -> str:
        numeros = list(dict.fromkeys(
            numero.strip().removeprefix("+") for numero in value.split(",") if numero.strip()
        ))
        if len(numeros) > 20 or any(not re.fullmatch(r"[1-9][0-9]{7,14}", numero) for numero in numeros):
            raise ValueError("Configure hasta 20 números internacionales separados por comas")
        return ",".join(numeros)

    @model_validator(mode="after")
    def validar_configuracion_whatsapp(self) -> "Settings":
        configuracion_completa = all((
            self.WHATSAPP_ACCESS_TOKEN and self.WHATSAPP_ACCESS_TOKEN.get_secret_value().strip(),
            self.WHATSAPP_PHONE_NUMBER_ID,
            self.WHATSAPP_API_VERSION,
            self.WHATSAPP_DESTINATARIOS,
        ))
        if self.WHATSAPP_ENABLED and not configuracion_completa:
            raise ValueError("WhatsApp requiere token, phone number ID, versión de API y destinatarios")
        if self.WHATSAPP_SOLICITUDES_ENABLED and not all((
            self.WHATSAPP_ACCESS_TOKEN and self.WHATSAPP_ACCESS_TOKEN.get_secret_value().strip(),
            self.WHATSAPP_PHONE_NUMBER_ID, self.WHATSAPP_API_VERSION, self.WHATSAPP_SOLICITUDES_DESTINATARIOS,
        )):
            raise ValueError("Avisos de solicitudes requieren token, emisor, versión y destinatarios")
        return self

    # Host y Puerto
    HOST: Optional[str] = None
    PORT: int = 8000

    CONTROL_MANTENCIONES_DIAS_RECIENTES: int = 14
    CONTROL_MANTENCIONES_VENTANA_DIAS: int = 90

    # JWT Security Settings
    SECRET_KEY: str = "narbus_secret_key_taller_2026_super_secure_jwt_token_change_in_prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: Optional[int] = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES
    REFRESH_TOKEN_EXPIRE_MINUTES: int = DEFAULT_REFRESH_TOKEN_EXPIRE_MINUTES

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
    MAX_VIDEO_UPLOAD_SIZE_BYTES: Optional[int] = DEFAULT_MAX_VIDEO_UPLOAD_SIZE_BYTES
    MAX_VIDEO_WIDTH: int = DEFAULT_MAX_VIDEO_WIDTH
    MAX_VIDEO_HEIGHT: int = DEFAULT_MAX_VIDEO_HEIGHT
    MAX_VIDEO_FPS: Optional[int] = DEFAULT_MAX_VIDEO_FPS
    MAX_VIDEO_DURATION_SECONDS: Optional[int] = DEFAULT_MAX_VIDEO_DURATION_SECONDS
    VIDEO_TRANSCODE_ENABLED: bool = True

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

    # Restricción perimetral: cualquier dispositivo; el control aplica al origen web.
    ENFORCE_MOBILE_ONLY: bool = False
    ENFORCE_ORIGIN_CHECK: bool = False
    APP_CLIENT_SECRET: Optional[str] = None  # Header opcional X-App-Client-Key para bypass o clientes de confianza

    # Tiempo real: la primera implementación funciona en una única instancia mediante memoria.
    REALTIME_ENABLED: bool = True
    REALTIME_BACKEND: str = "memory"
    REALTIME_HEARTBEAT_SECONDS: int = 25

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
        if self.FRONTEND_URL and self.FRONTEND_URL.strip():
            return None
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
    "DEFAULT_REFRESH_TOKEN_EXPIRE_MINUTES",
    "DEFAULT_MAX_UPLOAD_SIZE_BYTES",
    "DEFAULT_MAX_VIDEO_UPLOAD_SIZE_BYTES",
    "DEFAULT_MAX_VIDEO_WIDTH",
    "DEFAULT_MAX_VIDEO_HEIGHT",
    "DEFAULT_MAX_VIDEO_FPS",
    "DEFAULT_MAX_VIDEO_DURATION_SECONDS",
    "DEFAULT_SIGNED_URL_EXPIRATION_MINUTES",
]
