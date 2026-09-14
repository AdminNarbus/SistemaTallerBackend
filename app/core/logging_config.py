"""
logging_config.py
=================
Configurador central del sistema de logging para BackendTallerNarbus.

Uso:
    from app.core.logging_config import setup_logging
    setup_logging(environment=settings.ENVIRONMENT.value)

Se llama UNA SOLA VEZ al inicio de la aplicación (en app/main.py).
Todos los módulos obtienen su logger con: logging.getLogger(__name__)
"""
import logging
import logging.handlers
import os
import sys
from typing import Dict, Final

FMT_LOG: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATEFMT_LOG: Final[str] = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES: Final[int] = 5 * 1024 * 1024   # 5 MB
LOG_BACKUP_COUNT: Final[int] = 5
LOG_FILENAME: Final[str] = "narbus.log"

LEVEL_MAP: Final[Dict[str, int]] = {
    "dev_local": logging.DEBUG,
    "dev_lan": logging.DEBUG,
    "production": logging.WARNING,
}


def _build_console_handler(level: int) -> logging.StreamHandler:
    """Crea y formatea el manejador de logging para salida estándar."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(FMT_LOG, datefmt=DATEFMT_LOG))
    return handler


def _build_file_handler(environment: str, logs_dir: str) -> logging.handlers.RotatingFileHandler:
    """Crea y formatea el manejador de archivo con rotación automática."""
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, LOG_FILENAME)
    file_level = logging.INFO if environment != "production" else logging.WARNING

    handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(file_level)
    handler.setFormatter(logging.Formatter(FMT_LOG, datefmt=DATEFMT_LOG))
    return handler


def _configure_external_loggers(environment: str) -> None:
    """Ajusta niveles de ruido para bibliotecas de terceros."""
    if environment == "production":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    else:
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def setup_logging(environment: str = "dev_local") -> None:
    """Configura el sistema de logging global de la aplicación coordinando manejadores."""
    level = LEVEL_MAP.get(environment, logging.INFO)
    logs_dir = os.path.join(os.getcwd(), "logs")

    console_handler = _build_console_handler(level)
    file_handler = _build_file_handler(environment, logs_dir)

    logging.basicConfig(level=level, handlers=[console_handler, file_handler])
    _configure_external_loggers(environment)

    logging.getLogger(__name__).info(
        "[STARTUP] Logging configurado | entorno=%s | nivel=%s | archivo=%s",
        environment,
        logging.getLevelName(level),
        os.path.join(logs_dir, LOG_FILENAME),
    )


__all__ = [
    "setup_logging",
    "FMT_LOG",
    "DATEFMT_LOG",
    "LOG_MAX_BYTES",
    "LOG_BACKUP_COUNT",
    "LOG_FILENAME",
]

