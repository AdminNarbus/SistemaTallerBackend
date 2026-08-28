import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import AppEnvironment, settings
from app.core.database import engine
from app.core.db_patch import apply_db_patches
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manejo del ciclo de vida de la aplicación.
    La siembra de datos de prueba (seeding) SOLO ocurre en entorno local/desarrollo.
    """
    try:
        await apply_db_patches()

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
    except Exception as e:
        logger.critical(
            "[STARTUP] Error crítico durante el inicio de la aplicación: %s",
            e,
            exc_info=True,
        )
    
    yield
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
