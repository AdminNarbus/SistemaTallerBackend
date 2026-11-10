"""Compara únicamente el esquema del módulo con la metadata declarativa."""

import subprocess
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.models import Base


def incluir(objeto, nombre, tipo, reflejado, comparado):
    if tipo == "table":
        return nombre.startswith("control_") or nombre == "buses"
    if objeto.table.name == "buses":
        return tipo == "column" and nombre == "intervalo_mantencion_km"
    return True


async def test_esquema_alembic_del_modulo_sin_diferencias(pg_cluster):
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(pg_cluster[0])

    def comparar(connection):
        contexto = MigrationContext.configure(
            connection,
            opts={
                "include_object": incluir,
                "compare_type": True,
                "compare_server_default": True,
            },
        )
        assert compare_metadata(contexto, Base.metadata) == []
        checks = inspect(connection).get_check_constraints("buses")
        assert any(c["name"] == "ck_buses_intervalo_mantencion" for c in checks)

    try:
        async with engine.connect() as connection:
            await connection.run_sync(comparar)
    finally:
        await engine.dispose()
