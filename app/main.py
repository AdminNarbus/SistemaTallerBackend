import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import AppEnvironment, settings
from app.core.database import engine
from app.core.exceptions import (
    NarbusException,
    narbus_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)
from app.core.logging_config import setup_logging
from app.core.seed import seed_initial_data

# ─── Inicialización del logging (debe ejecutarse antes del lifespan) ─────────
setup_logging(environment=settings.ENVIRONMENT.value)
logger = logging.getLogger(__name__)


# Asegurar la existencia del directorio local para uploads/evidencias
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(os.path.join(UPLOAD_DIR, "evidencias"), exist_ok=True)


async def _neon_keepalive_loop():
    """
    Tarea en background que realiza un ping liviano cada 3 minutos a la BD en la nube.
    Evita que el cómputo serverless de Neon se suspenda por inactividad (timeout de 5 min)
    y previene el retraso inicial (cold-start) de 3 segundos en las peticiones.
    """
    while True:
        try:
            await asyncio.sleep(180)
            t0 = time.perf_counter()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            rtt_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "[KEEPALIVE] Pulso a Neon exitoso (compute activo 24/7) | rtt=%.1fms",
                rtt_ms,
            )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("[KEEPALIVE] Advertencia en ping de fondo: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manejo del ciclo de vida de la aplicación.
    La siembra de datos de prueba (seeding) SOLO ocurre en entorno local/desarrollo.
    """
    keepalive_task = None
    try:
        # Ejecutar siembra de datos únicamente en entorno de desarrollo local/LAN
        if settings.ENVIRONMENT in [AppEnvironment.DEV_LOCAL, AppEnvironment.DEV_LAN]:
            logger.info(
                "[STARTUP] Entorno '%s': Ejecutando siembra de datos de prueba...",
                settings.ENVIRONMENT.value,
            )
            await seed_initial_data()
        else:
            logger.info(
                "[STARTUP] Entorno '%s': Siembra de datos omitida (entorno productivo).",
                settings.ENVIRONMENT.value,
            )

        # Pre-calentar el pool de conexiones e iniciar keep-alive si se usa BD remota
        if "sqlite" not in settings.async_database_url:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("[STARTUP] Pool de base de datos pre-calentado e iniciado.")
            keepalive_task = asyncio.create_task(_neon_keepalive_loop())
    except Exception as e:
        logger.critical(
            "[STARTUP] Error crítico durante el inicio de la aplicación: %s",
            e,
            exc_info=True,
        )
    
    yield
    if keepalive_task:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.docs_url else None,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS],
    allow_origin_regex=settings.effective_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests_timing_middleware(request, call_next):
    """Mide y registra con precisión de milisegundos el tiempo de respuesta de cada endpoint."""
    t_start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - t_start) * 1000.0
    logger.info(
        "[HTTP] %s %s | status=%s | duracion=%.1fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

# ─── Exception Handlers Globales ────────────────────────────────────────────
# El orden de registro importa: del más específico al más genérico.
app.add_exception_handler(NarbusException, narbus_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "environment": settings.ENVIRONMENT.value,
        "docs": settings.docs_url or "Disabled",
        "health": f"{settings.API_V1_STR}/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.PORT,
        reload=settings.is_reload_enabled,
    )
