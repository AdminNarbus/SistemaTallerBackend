import logging
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", summary="Health check endpoint")
async def health_check():
    return {"status": "ok", "service": "Backend Taller Narbus"}


@router.get("/health/db", summary="Database connection health check")
async def db_health_check(db: AsyncSession = SessionDep):
    """
    Verifica la conectividad activa con el motor de base de datos.
    Retorna 200 OK si la conexión es exitosa, o 503 Service Unavailable
    con mensaje seguro (sin exponer stack traces) si hay fallos.
    """
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error("[HEALTH] Error de verificación en base de datos: %s", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "detail": "Error de conexión con la base de datos.",
            },
        )
