"""
Script de mantenimiento y limpieza:
Elimina la totalidad de Órdenes de Trabajo (taller_solicitudes) y sus registros dependientes
en la base de datos configurada (Neon), además de restablecer en_taller = false en la flota de buses.
"""
import sys
from pathlib import Path

# Asegurar importación de app al ejecutar el script directamente
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TABLAS_DEPENDIENTES = [
    "taller_asignacion_fallas",
    "taller_solicitud_comentarios",
    "taller_solicitud_mecanicos",
    "taller_solicitud_detalles",
    "taller_solicitud_pauta",
    "taller_solicitud_evidencias",
    "taller_solicitud_estadias",
]

async def eliminar_todas_las_ots() -> None:
    target_url = settings.async_database_url
    logger.info("Conectando a base de datos: %s", target_url.split("@")[-1] if "@" in target_url else target_url)

    engine = create_async_engine(target_url)
    sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with sessionmaker() as session:
        async with session.begin():
            # 1. Contar OTs actuales
            res_ots = await session.execute(text("SELECT count(*) FROM taller_solicitudes;"))
            total_ots = res_ots.scalar()
            logger.info("Total de OTs encontradas: %d", total_ots)

            # 2. Contar y actualizar buses con en_taller = true
            res_buses = await session.execute(text("SELECT count(*) FROM buses WHERE en_taller = true;"))
            buses_en_taller = res_buses.scalar()
            logger.info("Buses marcados con en_taller=true: %d", buses_en_taller)

            if buses_en_taller > 0:
                await session.execute(text("UPDATE buses SET en_taller = false WHERE en_taller = true;"))
                logger.info("Estado en_taller restablecido a false para %d buses.", buses_en_taller)

            # 3. Eliminar tablas hijas de manera explícita (respetando dependencias si las hubiera)
            for tabla in TABLAS_DEPENDIENTES:
                try:
                    res_del = await session.execute(text(f"DELETE FROM {tabla};"))
                    logger.info("Registros eliminados en %s: %s", tabla, res_del.rowcount)
                except Exception as e:
                    logger.warning("No se pudo limpiar %s directamente o la tabla no existe: %s", tabla, e)

            # 4. Eliminar las OTs maestras
            res_del_ots = await session.execute(text("DELETE FROM taller_solicitudes;"))
            logger.info("Registros eliminados en taller_solicitudes: %s", res_del_ots.rowcount)

            # 5. Opcional: reiniciar secuencias de autoincremento para empezar limpias desde 1
            for tabla in ["taller_solicitudes"] + TABLAS_DEPENDIENTES:
                try:
                    await session.execute(text(f"ALTER SEQUENCE IF EXISTS {tabla}_id_seq RESTART WITH 1;"))
                except Exception as e:
                    logger.debug("No se pudo reiniciar secuencia para %s: %s", tabla, e)

        # 6. Verificación posterior a la transacción
        logger.info("=== VERIFICACIÓN POSTERIOR ===")
        res_post_ots = await session.execute(text("SELECT count(*) FROM taller_solicitudes;"))
        logger.info("OTs restantes en taller_solicitudes: %d", res_post_ots.scalar())

        res_post_buses = await session.execute(text("SELECT count(*) FROM buses WHERE en_taller = true;"))
        logger.info("Buses con en_taller=true restantes: %d", res_post_buses.scalar())

    await engine.dispose()
    logger.info("Proceso de eliminación finalizado exitosamente.")

if __name__ == "__main__":
    asyncio.run(eliminar_todas_las_ots())
