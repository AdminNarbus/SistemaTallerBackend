"""Vincula exclusivamente la OT artificial 35 al bus de prueba con ID generado."""

import asyncio
import argparse
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.config import settings
from app.core.exceptions import BusinessRuleException
from app.modules.buses.models.bus import Bus
from app.modules.buses.repository.bus_repository import bus_repository
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.repository.taller_repository import taller_repository

logger = logging.getLogger(__name__)
PATENTE_PRUEBA = "TEST-BUS-1"


async def asegurar_bus_prueba(db: AsyncSession) -> Bus:
    """Crea o reutiliza solo el vehículo ficticio, sin fijar su clave primaria."""
    await taller_repository.lock_bus_cycle(db, None, "1")
    bus = await bus_repository.get_by_n_bus(db, "1")
    if bus is not None and bus.patente != PATENTE_PRUEBA:
        raise BusinessRuleException("El número 1 pertenece a otro vehículo; no se modifica")
    if bus is None:
        if await bus_repository.get_by_patente(db, PATENTE_PRUEBA):
            raise BusinessRuleException("La patente de prueba ya pertenece a otro número")
        bus = Bus(n_bus="1", patente=PATENTE_PRUEBA, tipo_bus="PRUEBA FICTICIA", is_active=True, en_taller=False)
        db.add(bus)
        await db.flush()
    return bus


async def reparar_ot_prueba(db: AsyncSession) -> int:
    ot = await db.scalar(select(TallerSolicitud).where(TallerSolicitud.id == 35).with_for_update())
    if ot is None or "Bus 1 ficticio" not in (ot.descripcion_general or ""):
        raise BusinessRuleException("La OT 35 no es la prueba artificial esperada")
    bus = await asegurar_bus_prueba(db)
    if ot.bus_id is not None and ot.bus_id != bus.id:
        raise BusinessRuleException("La OT ya apunta a otro vehículo; no se modifica")
    ot.bus_id = bus.id
    await db.flush()
    if await taller_repository.tiene_estadia_abierta_bus(db, bus.id):
        bus.en_taller = True
    return bus.id


async def main() -> None:
    engine = create_async_engine(settings.async_database_url, connect_args={"timeout": 15})
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            async with db.begin():
                bus_id = await reparar_ot_prueba(db)
            logger.info("OT 35 vinculada a bus de prueba | numero=1 | bus_id=%s | patente=%s", bus_id, PATENTE_PRUEBA)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Crear el bus ficticio y vincular exclusivamente la OT artificial 35")
    if parser.parse_args().apply:
        asyncio.run(main())
    else:
        logger.info("Sin cambios. Para aplicar la reparación autorizada, ejecutar con --apply.")
