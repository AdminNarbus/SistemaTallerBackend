import os
from enum import Enum
from typing import List, Union, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(str, Enum):
    DEV_LOCAL = "dev_local"
    DEV_LAN = "dev_lan"
    PRODUCTION = "production"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Backend Taller Narbus"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Perfil / Entorno de ejecución
    ENVIRONMENT: AppEnvironment = AppEnvironment.DEV_LOCAL

    # Host y Puerto
    HOST: Optional[str] = None
    PORT: int = 8000

    # JWT Security Settings
    SECRET_KEY: str = "narbus_secret_key_taller_2026_super_secure_jwt_token_change_in_prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas por defecto

    # PostgreSQL Database Settings
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "taller_narbus"

    DATABASE_URL: Optional[str] = None

    # CORS Settings
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
    ]

    CORS_ORIGIN_REGEX: Optional[str] = None

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

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
    def effective_cors_origin_regex(self) -> Optional[str]:
        if self.CORS_ORIGIN_REGEX:
            return self.CORS_ORIGIN_REGEX
        if self.ENVIRONMENT in (AppEnvironment.DEV_LAN, AppEnvironment.DEV_LOCAL):
            return r"^(https?://.*|http://.*|capacitor://.*)$"
        return None


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
