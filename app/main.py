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
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import AppEnvironment, settings
from app.core.database import engine
from app.core.db_metrics import begin_request_metrics, end_request_metrics
from app.core.exceptions import (
    NarbusException,
    narbus_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
    integrity_exception_handler,
)
from app.core.logging_config import setup_logging
from app.core.seed import seed_initial_data
from app.core.middleware.device_restriction import DeviceRestrictionMiddleware
from app.core.realtime.runtime import realtime_runtime
from app.core.realtime.router import router as realtime_router
from app.core.realtime.http_events import emit_http_mutation_event

# ─── Inicialización del logging (debe ejecutarse antes del lifespan) ─────────
setup_logging(environment=settings.ENVIRONMENT.value)
logger = logging.getLogger(__name__)


# Asegurar la existencia del directorio de almacenamiento (volumen montado en Cloud Run o disco local)
UPLOAD_DIR = settings.upload_absolute_path
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "solicitudes"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "evidencias"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "neumaticos"), exist_ok=True)
logger.info("[STARTUP] Directorio de almacenamiento de imágenes listo: '%s'", UPLOAD_DIR)


KEEPALIVE_INTERVAL_SECONDS = 120


async def _neon_keepalive_loop(stop_event: asyncio.Event):
    """
    Tarea en background que realiza un ping liviano cada 2 minutos a la BD en la nube.
    Evita que el cómputo serverless de Neon se suspenda por inactividad (timeout de 5 min)
    y previene el retraso inicial (cold-start) de 3 segundos en las peticiones.
    """
    from app.core.database import AsyncSessionLocal
    while True:
        try:
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=KEEPALIVE_INTERVAL_SECONDS
                )
                break
            except asyncio.TimeoutError:
                pass
            t0 = time.perf_counter()
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
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
    keepalive_stop = asyncio.Event()
    if settings.REALTIME_ENABLED:
        await realtime_runtime.start()
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
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            logger.info("[STARTUP] Pool de base de datos pre-calentado e iniciado.")
            # Una sola tarea por proceso y ciclo de vida. El lock distribuido de
            # Alembic/seed evita que las inicializaciones de BD compitan entre sí.
            keepalive_task = asyncio.create_task(
                _neon_keepalive_loop(keepalive_stop),
                name="narbus-neon-keepalive",
            )
    except Exception as e:
        logger.critical(
            "[STARTUP] Error crítico durante el inicio de la aplicación: %s",
            e,
            exc_info=True,
        )
    
    yield
    if settings.REALTIME_ENABLED:
        await realtime_runtime.stop()
    if keepalive_task:
        keepalive_stop.set()
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
    allow_origins=[str(origin).rstrip("/") for origin in settings.effective_cors_origins],
    allow_origin_regex=settings.effective_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-DB-Round-Trips"],
)

app.add_middleware(DeviceRestrictionMiddleware)


@app.middleware("http")
async def log_requests_timing_middleware(request, call_next):
    """Mide y registra con precisión de milisegundos el tiempo de respuesta de cada endpoint."""
    t_start = time.perf_counter()
    metrics_token = begin_request_metrics()
    response = None
    try:
        response = await call_next(request)
        emit_http_mutation_event(request, response.status_code)
        return response
    finally:
        metrics = end_request_metrics(metrics_token)
        duration_ms = (time.perf_counter() - t_start) * 1000.0
        round_trips = metrics.round_trips if metrics else 0
        db_time_ms = metrics.time_ms if metrics else 0.0
        cache_status = metrics.user_cache if metrics else None
        if response and settings.ENVIRONMENT != AppEnvironment.PRODUCTION:
            response.headers["X-DB-Round-Trips"] = str(round_trips)
        logger.info(
            "[HTTP] %s %s | status=%s | duracion=%.1fms | db_round_trips=%s | db_time=%.1fms | user_cache=%s",
            request.method,
            request.url.path,
            response.status_code if response else "error",
            duration_ms,
            round_trips,
            db_time_ms,
            cache_status or "n/a",
        )
        if request.url.path.startswith(f"{settings.API_V1_STR}/taller/"):
            budget = 1 if request.method == "GET" else 2
            # El perfil sólo agrega un viaje aceptado cuando la caché está fría.
            if cache_status == "miss":
                budget += 1
            if round_trips > budget:
                logger.warning(
                    "[DB-BUDGET] %s excedió presupuesto de %s viajes: %s",
                    request.url.path,
                    budget,
                    round_trips,
                )

# ─── Exception Handlers Globales ────────────────────────────────────────────
# El orden de registro importa: del más específico al más genérico.
app.add_exception_handler(NarbusException, narbus_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)
app.add_exception_handler(IntegrityError, integrity_exception_handler)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(realtime_router, prefix=settings.API_V1_STR)


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
