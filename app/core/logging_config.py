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


# ─────────────────────────────────────────────────────────
# Formatos
# ─────────────────────────────────────────────────────────

_FMT_DEV = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# ─────────────────────────────────────────────────────────
# Niveles por entorno
# ─────────────────────────────────────────────────────────

_LEVEL_MAP = {
    "dev_local": logging.DEBUG,
    "dev_lan": logging.DEBUG,
    "production": logging.WARNING,
}


def setup_logging(environment: str = "dev_local") -> None:
    """
    Configura el sistema de logging global de la aplicación.

    - Consola (StreamHandler): siempre activo.
        · dev_local / dev_lan → formato legible con nivel DEBUG.
        · production          → formato legible con nivel WARNING.
    - Archivo (RotatingFileHandler): activo en todos los entornos.
        · Ruta: <cwd>/logs/narbus.log
        · Rotación: 5 MB por archivo, máximo 5 archivos de respaldo.
        · Nivel: INFO en dev, WARNING en production.
    """
    level = _LEVEL_MAP.get(environment, logging.INFO)

    # ── Handler de consola ──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(_FMT_DEV, datefmt=_DATEFMT))

    # ── Handler de archivo con rotación ──
    logs_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, "narbus.log")

    file_level = logging.INFO if environment != "production" else logging.WARNING
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(_FMT_DEV, datefmt=_DATEFMT))

    # ── Configuración del logger raíz ──
    logging.basicConfig(
        level=level,
        handlers=[console_handler, file_handler],
    )

    # Silenciar loggers ruidosos de librerías externas en producción
    if environment == "production":
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    else:
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "[STARTUP] Logging configurado | entorno=%s | nivel=%s | archivo=%s",
        environment,
        logging.getLevelName(level),
        log_file,
    )
