import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.models.base import Base


# Asegurar la existencia del directorio local para uploads/evidencias
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(os.path.join(UPLOAD_DIR, "evidencias"), exist_ok=True)


async def seed_initial_users():
    try:
        from app.core.database import AsyncSessionLocal
        from app.crud.crud_usuario import crear_usuario, get_usuario_by_username
        from app.schemas.usuario import UsuarioCreate

        async with AsyncSessionLocal() as db:
            if not await get_usuario_by_username(db, "admin"):
                await crear_usuario(
                    db,
                    UsuarioCreate(
                        username="admin",
                        password="admin123",
                        rol="ADMIN",
                    ),
                )
                print("✅ Seed: Usuario 'admin' creado automáticamente (Password: admin123).")

            if not await get_usuario_by_username(db, "chofer1"):
                await crear_usuario(
                    db,
                    UsuarioCreate(
                        username="chofer1",
                        password="chofer123",
                        rol="CONDUCTOR",
                    ),
                )
                print("✅ Seed: Usuario 'chofer1' creado automáticamente (Password: chofer123).")
    except Exception as e:
        print(f"⚠️ Error al sembrar usuarios iniciales: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: Try creating tables if database is available
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_initial_users()
    except Exception as e:
        print(f"[WARNING] Could not connect to PostgreSQL database on startup: {e}")
        print("Please verify PostgreSQL is running and check your .env configuration.")
    yield
    # Shutdown logic: Dispose database engine connections
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.docs_url else None,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    lifespan=lifespan,
)

# Configurar middleware CORS dinámico según perfil
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS],
    allow_origin_regex=settings.effective_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Montar directorio estático de uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Include API Router
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
