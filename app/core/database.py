from typing import AsyncGenerator, Final
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

DEFAULT_DB_POOL_SIZE: Final[int] = 10
DEFAULT_DB_MAX_OVERFLOW: Final[int] = 20
DEFAULT_DB_POOL_RECYCLE_SECONDS: Final[int] = 300
DEFAULT_DB_POOL_TIMEOUT_SECONDS: Final[int] = 30

engine_kwargs = {
    "echo": False,
    "future": True,
    "pool_pre_ping": False,  # Desactivado para eliminar latencia de 160ms por ping en cada checkout
}
if "sqlite" not in settings.async_database_url:
    engine_kwargs.update(
        {
            "pool_size": DEFAULT_DB_POOL_SIZE,
            "max_overflow": DEFAULT_DB_MAX_OVERFLOW,
            "pool_recycle": DEFAULT_DB_POOL_RECYCLE_SECONDS,
            "pool_timeout": DEFAULT_DB_POOL_TIMEOUT_SECONDS,
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
        yield session


__all__ = [
    "engine",
    "AsyncSessionLocal",
    "get_db",
    "DEFAULT_DB_POOL_SIZE",
    "DEFAULT_DB_MAX_OVERFLOW",
    "DEFAULT_DB_POOL_RECYCLE_SECONDS",
    "DEFAULT_DB_POOL_TIMEOUT_SECONDS",
]

