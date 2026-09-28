"""
Script de saneamiento de datos para taller_solicitud_estadias:
Elimina estadías abiertas duplicadas espurias conservando únicamente la primera estadía
legítima abierta por solicitud y corrigiendo el numero_visita correlativo.
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from app.core.config import settings

async def sanear_estadias_duplicadas(target_url: str):
    print(f"Iniciando saneamiento en: {target_url.split('@')[-1] if '@' in target_url else target_url}")
    engine = create_async_engine(target_url)
    sessionmaker = async_sessionmaker(bind=engine, class_=AsyncSession)
    
    async with sessionmaker() as session:
        # 1. Encontrar solicitudes con más de 1 estadía abierta (fecha_salida IS NULL)
        stmt_find = text("""
            SELECT solicitud_id, ARRAY_AGG(id ORDER BY id ASC) as ids
            FROM taller_solicitud_estadias
            WHERE fecha_salida IS NULL
            GROUP BY solicitud_id
            HAVING COUNT(*) > 1;
        """)
        res = await session.execute(stmt_find)
        rows = res.fetchall()
        print(f"Solicitudes afectadas encontradas: {len(rows)}")

        for r in rows:
            solicitud_id = r.solicitud_id
            estadia_ids = r.ids
            # El primero es el legítimo
            id_mantener = estadia_ids[0]
            ids_eliminar = estadia_ids[1:]
            print(f"OT #{solicitud_id}: Mantener estadía ID {id_mantener}, eliminando duplicados espurios IDs {ids_eliminar}")
            
            await session.execute(
                text("DELETE FROM taller_solicitud_estadias WHERE id = ANY(:del_ids);"),
                {"del_ids": ids_eliminar}
            )

        # 2. Corregir correlativo numero_visita en caso de inconsistencias
        stmt_sols = text("SELECT DISTINCT solicitud_id FROM taller_solicitud_estadias ORDER BY solicitud_id ASC;")
        res_sols = await session.execute(stmt_sols)
        all_sols = [s[0] for s in res_sols.fetchall()]

        for s_id in all_sols:
            res_ests = await session.execute(
                text("SELECT id FROM taller_solicitud_estadias WHERE solicitud_id = :sid ORDER BY fecha_ingreso ASC, id ASC;"),
                {"sid": s_id}
            )
            est_rows = res_ests.fetchall()
            for idx, est_r in enumerate(est_rows, start=1):
                await session.execute(
                    text("UPDATE taller_solicitud_estadias SET numero_visita = :vis WHERE id = :eid AND numero_visita != :vis;"),
                    {"vis": idx, "eid": est_r[0]}
                )

        await session.commit()
        print("Saneamiento completado con éxito.")
    await engine.dispose()

if __name__ == "__main__":
    neon_url = "postgresql+asyncpg://neondb_owner:npg_2tLr1bFnPmWl@ep-misty-hill-ajku6flk-pooler.c-3.us-east-2.aws.neon.tech/taller?ssl=require"
    asyncio.run(sanear_estadias_duplicadas(neon_url))
