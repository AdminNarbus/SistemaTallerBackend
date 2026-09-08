from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine_kwargs = {
    "echo": False,
    "future": True,
    "pool_pre_ping": True,
}
if "sqlite" not in settings.async_database_url:
    engine_kwargs.update(
        {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_recycle": 300,
            "pool_timeout": 30,
        }
    )

engine = create_async_engine(
    settings.async_database_url,
    **engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session for FastAPI endpoints."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
