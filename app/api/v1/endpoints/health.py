from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import SessionDep

router = APIRouter()


@router.get("/health", summary="Health check endpoint")
async def health_check():
    return {"status": "ok", "service": "Backend Taller Narbus"}


@router.get("/health/db", summary="Database connection health check")
async def db_health_check(db: AsyncSession = SessionDep):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}
