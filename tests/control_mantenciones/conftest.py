"""PostgreSQL desechable: jamás utiliza la base configurada de la aplicación."""

import importlib.util
import os
from pathlib import Path
import subprocess

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.control_mantenciones.models.entities import (
    ControlEvento as Evento,
    ControlKilometraje as Km,
    ControlMantencion as Mant,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def pg_cluster():
    spec = importlib.util.spec_from_file_location(
        "pg_control", ROOT / "tests/migrations/test_jsonb_migrations.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    binaries = list(Path("C:/Program Files/PostgreSQL").glob("*/bin/initdb.exe"))
    if not binaries:
        pytest.skip("No están disponibles los binarios locales de PostgreSQL.")
    module.PG_BIN = sorted(binaries, reverse=True)[0].parent
    module.JsonCompatibility.setUpClass()
    cluster = module.JsonCompatibility()
    url = f"postgresql+asyncpg://migration_test@127.0.0.1:{cluster.port}/postgres"
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "ENVIRONMENT": "dev_local",
        "SEED_ON_STARTUP": "false",
    }
    try:

        def migrate(*args):
            result = subprocess.run(
                [str(ROOT / ".venv/Scripts/python.exe"), "-m", "alembic", *args],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            assert result.returncode == 0, (result.stderr + result.stdout)[-6000:]

        migrate("upgrade", "head")
        migrate("downgrade", "-1")
        migrate("upgrade", "head")
        assert (
            cluster.sql(
                "SELECT (SELECT count(*) FROM control_mantenciones) + (SELECT count(*) FROM control_kilometrajes) + (SELECT count(*) FROM control_mantenciones_eventos)"
            )
            == "0"
        )
        yield url, env
    finally:
        module.JsonCompatibility.doClassCleanups()


@pytest.fixture
async def sesiones(pg_cluster):
    engine = create_async_engine(pg_cluster[0])
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        await db.execute(update(Evento).values(kilometraje_id=None))
        await db.execute(delete(Km))
        await db.execute(delete(Evento))
        await db.execute(delete(Mant))
        actor = await db.get(Usuario, 900001)
        if actor is None:
            await db.execute(
                update(Bus).values(n_bus=func.concat("BASE-", Bus.id), is_active=False)
            )
            rol_id = await db.scalar(select(Rol.id).where(Rol.nombre == "ADMIN"))
            db.add(
                Usuario(
                    id=900001,
                    username="control_test",
                    nombre="Prueba",
                    password_hash="sin-acceso",
                    rol_id=rol_id,
                    is_active=True,
                )
            )
            db.add_all(
                [
                    Bus(
                        id=900001,
                        n_bus="354",
                        patente="CONTROL354",
                        marca="Mercedes",
                        is_active=True,
                    ),
                    Bus(
                        id=900002,
                        n_bus="356",
                        patente="CONTROL356",
                        marca="Scania",
                        is_active=True,
                    ),
                ]
            )
        else:
            bus = await db.get(Bus, 900001)
            bus.intervalo_mantencion_km = None
        await db.commit()
    try:
        yield factory
    finally:
        await engine.dispose()
