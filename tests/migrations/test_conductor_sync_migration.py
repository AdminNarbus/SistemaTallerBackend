import importlib.util
import io
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from test_motivo_salida_estadia import postgres_temporal


def migration_sql(direction):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/039_conductor_sync.py"
    spec = importlib.util.spec_from_file_location("conductor_sync_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        getattr(module, direction)()
    return output.getvalue()


def test_registro_mes_unico_y_ciclo_migracion(postgres_temporal):
    pg = postgres_temporal
    pg.sql(migration_sql("upgrade"))
    pg.sql("INSERT INTO conductor_sync (periodo,resultado) VALUES ('2026-11','{}')")
    with pytest.raises(AssertionError):
        pg.sql("INSERT INTO conductor_sync (periodo,resultado) VALUES ('2026-11','{}')")
    assert pg.sql("SELECT count(*) FROM conductor_sync WHERE created_at IS NOT NULL AND updated_at IS NOT NULL") == "1"
    pg.sql(migration_sql("downgrade"))
    pg.sql(migration_sql("upgrade"))
    assert pg.sql("SELECT count(*) FROM conductor_sync") == "0"


async def test_sincronizacion_postgres_atomica_e_idempotente(postgres_temporal, monkeypatch):
    from unittest.mock import AsyncMock
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.base import Base
    from app.modules.auth.models.rol import Rol
    from app.modules.auth.models.usuario import Usuario
    from app.modules.auth.models.conductor_sync import ConductorSync
    from app.modules.auth.services import conductor_sync_service as service
    from app.modules.auth.services.conductor_source import validar_conductores

    pg = postgres_temporal
    engine = create_async_engine(f"postgresql+asyncpg://migration_test@127.0.0.1:{pg.port}/postgres")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    fuente = AsyncMock(return_value=validar_conductores([
        {"rut": "12345678-K", "nombre": "Juan", "apellido": "Perez", "activo": False},
        {"rut": "11222333-4", "nombre": "Ana", "apellido": "Lopez", "activo": True},
        {"rut": "9988877-6", "nombre": "Admin", "apellido": "Protegido", "activo": False},
    ]))
    monkeypatch.setattr(service, "obtener_conductores", fuente)
    monkeypatch.setattr(service, "get_password_hash", lambda password: f"hash:{password}")
    monkeypatch.setattr(service, "verify_password", lambda password, hashed: hashed == f"hash:{password}")
    monkeypatch.setattr(service.conductor_sync_service, "_notificar", AsyncMock())
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[Rol.__table__, Usuario.__table__]))
    try:
        async with session_factory() as db:
            db.add_all([Rol(id=1, nombre="CONDUCTOR"), Rol(id=2, nombre="ADMIN")])
            await db.flush()
            db.add_all([
                Usuario(username="12.345.678-k", rol_id=1, password_hash="anterior", is_active=True, telefono="123"),
                Usuario(username="9988877-6", rol_id=2, password_hash="admin", is_active=True),
                Usuario(username="8877766-5", rol_id=1, password_hash="ausente", is_active=True),
            ])
            await db.commit()
        async with session_factory() as db:
            resultado = await service.conductor_sync_service.sincronizar(db)
            assert (resultado.creados, resultado.actualizados, resultado.omitidos_otro_rol) == (1, 1, 1)
        async with session_factory() as db:
            usuarios = {user.username: user for user in (await db.execute(select(Usuario))).scalars()}
            assert usuarios["12345678-K"].password_hash == "hash:1234"
            assert usuarios["12345678-K"].telefono == "123"
            assert not usuarios["12345678-K"].is_active
            assert usuarios["11222333-4"].password_hash == "hash:1122"
            assert usuarios["9988877-6"].password_hash == "admin"
            assert usuarios["9988877-6"].is_active
            assert usuarios["8877766-5"].is_active
            assert await db.scalar(select(func.count()).select_from(ConductorSync)) == 1
        async with session_factory() as db:
            repetido = await service.conductor_sync_service.sincronizar(db)
            assert repetido.estado == "ya_ejecutado"
            fuente.assert_awaited_once()

        # Un fallo luego del flush debe revertir tanto usuarios como registro mensual.
        from sqlalchemy import delete
        async with session_factory() as db:
            await db.execute(delete(ConductorSync))
            await db.commit()
        fuente.return_value = validar_conductores([
            {"rut": "12345678-K", "nombre": "Modificado", "apellido": "Perez", "activo": True},
        ])
        async def fallar_commit(db, registro):
            db.add(registro)
            await db.flush()
            raise RuntimeError("Fallo simulado antes de commit")
        monkeypatch.setattr(service.repository, "guardar", fallar_commit)
        async with session_factory() as db:
            with pytest.raises(RuntimeError):
                await service.conductor_sync_service.sincronizar(db)
        async with session_factory() as db:
            usuario = await db.scalar(select(Usuario).where(Usuario.username == "12345678-K"))
            assert usuario.nombre == "Juan"
            assert not usuario.is_active
            assert await db.scalar(select(func.count()).select_from(ConductorSync)) == 0

        # El script usa el último estado de la fuente y también actualiza existentes,
        # sin depender del registro mensual ni consultar su calendario.
        from app.modules.auth.services.conductor_source import preparar_conductores
        datos, _ = preparar_conductores([
            {"rut": "12345678-K", "nombre": "Juan", "apellido": "Perez", "activo": False},
            {"rut": "12345678-K", "nombre": "Juan", "apellido": "Perez", "activo": True},
            {"rut": "11222333-4", "nombre": "Ana", "apellido": "Lopez", "activo": False},
            {"rut": "17666555-4", "nombre": "Nuevo", "apellido": None, "activo": False},
        ])
        async with session_factory() as db:
            resultado = await service.conductor_sync_service.sincronizar_ahora(db, datos)
            assert resultado.creados == 1
            assert resultado.habilitados == 1
            assert resultado.inhabilitados == 1
        async with session_factory() as db:
            usuarios = {user.username: user for user in (await db.execute(select(Usuario))).scalars()}
            assert usuarios["12345678-K"].is_active
            assert not usuarios["11222333-4"].is_active
            assert not usuarios["17666555-4"].is_active
            assert usuarios["17666555-4"].apellido == ""
            assert usuarios["9988877-6"].is_active
            assert usuarios["8877766-5"].is_active
            assert await db.scalar(select(func.count()).select_from(ConductorSync)) == 0
    finally:
        await engine.dispose()
