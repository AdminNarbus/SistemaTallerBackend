import asyncio
import os
import pytest
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.base import Base
import app.models  # asegura la carga de todos los modelos en Base.metadata
import app.modules.mantencion.models

from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.models.rol import Rol
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Crea una base de datos en memoria limpia para cada prueba."""
    from app.api.deps import clear_user_cache
    from app.modules.mantencion.repository.mantencion_repository import clear_mantencion_repository_caches

    clear_user_cache()
    clear_mantencion_repository_caches()

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Sobrescribir la dependencia get_db de FastAPI
        async def _override_get_db():
            yield session

        app.dependency_overrides[get_db] = _override_get_db
        yield session
        app.dependency_overrides.clear()

    clear_user_cache()
    clear_mantencion_repository_caches()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Cliente HTTPX asíncrono configurado para consultar la app de FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def seed_test_data(db_session: AsyncSession):
    """Siembra usuarios base con distintas funciones y catálogos de mantención."""
    # Roles
    rol_conductor = Rol(id=1, nombre="CONDUCTOR", descripcion="Conductor de bus")
    rol_mecanico = Rol(id=2, nombre="MECANICO", descripcion="Mecánico de taller")
    rol_supervisor = Rol(id=3, nombre="SUPERVISOR", descripcion="Supervisor de taller")
    rol_admin = Rol(id=4, nombre="ADMIN", descripcion="Administrador")
    db_session.add_all([rol_conductor, rol_mecanico, rol_supervisor, rol_admin])
    await db_session.flush()

    pwd_hash = get_password_hash("password123")

    # Usuarios
    user_conductor = Usuario(
        id=1,
        nombre="Juan",
        apellido="Conductor",
        username="conductor@narbus.cl",
        password_hash=pwd_hash,
        rol_id=1,
        is_active=True,
    )
    user_mecanico1 = Usuario(
        id=2,
        nombre="Pedro",
        apellido="Mecanico",
        username="mecanico1@narbus.cl",
        password_hash=pwd_hash,
        rol_id=2,
        is_active=True,
    )
    user_mecanico2 = Usuario(
        id=3,
        nombre="Carlos",
        apellido="Mecanico",
        username="mecanico2@narbus.cl",
        password_hash=pwd_hash,
        rol_id=2,
        is_active=True,
    )
    user_supervisor = Usuario(
        id=4,
        nombre="Roberto",
        apellido="Supervisor",
        username="supervisor@narbus.cl",
        password_hash=pwd_hash,
        rol_id=3,
        is_active=True,
    )
    user_inactive = Usuario(
        id=5,
        nombre="Inactivo",
        apellido="User",
        username="inactivo@narbus.cl",
        password_hash=pwd_hash,
        rol_id=1,
        is_active=False,
    )

    db_session.add_all([user_conductor, user_mecanico1, user_mecanico2, user_supervisor, user_inactive])

    # Catálogos de Mantención
    cat1 = CategoriaFalla(id=1, nombre="Motor", is_active=True)
    cat2 = CategoriaFalla(id=2, nombre="Frenos", is_active=True)
    db_session.add_all([cat1, cat2])
    await db_session.flush()

    falla1 = FallaTaller(id=1, categoria_id=1, nombre="Fuga de refrigerante", is_active=True)
    falla2 = FallaTaller(id=2, categoria_id=2, nombre="Desgaste de pastillas", is_active=True)
    db_session.add_all([falla1, falla2])

    await db_session.commit()

    # Re-fetch models with relationships initialized
    await db_session.refresh(user_conductor)
    await db_session.refresh(user_mecanico1)
    await db_session.refresh(user_mecanico2)
    await db_session.refresh(user_supervisor)

    return {
        "conductor": user_conductor,
        "mecanico1": user_mecanico1,
        "mecanico2": user_mecanico2,
        "supervisor": user_supervisor,
        "inactivo": user_inactive,
        "falla1": falla1,
        "falla2": falla2,
    }


@pytest.fixture
def auth_headers_conductor(seed_test_data):
    token = create_access_token(subject=1)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_mecanico1(seed_test_data):
    token = create_access_token(subject=2)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_mecanico2(seed_test_data):
    token = create_access_token(subject=3)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_supervisor(seed_test_data):
    token = create_access_token(subject=4)
    return {"Authorization": f"Bearer {token}"}
