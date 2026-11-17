from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictException
from app.modules.auth.dtos.conductor_sync_dto import normalizar_rut
from app.modules.auth.models.conductor_sync import ConductorSync
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario

SYNC_LOCK_ID = 760006
QUERY_BATCH_SIZE = 500


class ConductorSyncRepository:
    async def bloquear(self, db: AsyncSession) -> None:
        # PostgreSQL libera el lock incluso si el worker muere antes del commit.
        result = await db.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": SYNC_LOCK_ID}
        )
        if not result.scalar_one():
            raise ConflictException("Ya hay una sincronización de conductores en curso.")

    async def obtener_ejecucion(self, db: AsyncSession, periodo: str) -> ConductorSync | None:
        return await db.get(ConductorSync, periodo)

    async def obtener_rol(self, db: AsyncSession) -> Rol:
        result = await db.execute(select(Rol).where(Rol.nombre == "CONDUCTOR"))
        rol = result.scalar_one_or_none()
        if rol is None:
            rol = Rol(nombre="CONDUCTOR", descripcion="Conductor de buses")
            db.add(rol)
            await db.flush()
        return rol

    async def obtener_usuarios(self, db: AsyncSession, ruts: list[str]) -> dict[str, Usuario]:
        usuarios = {}
        username_normalizado = func.upper(func.replace(func.trim(Usuario.username), ".", ""))
        for start in range(0, len(ruts), QUERY_BATCH_SIZE):
            result = await db.execute(select(Usuario).options(joinedload(Usuario.rol_rel)).where(
                username_normalizado.in_(ruts[start:start + QUERY_BATCH_SIZE])
            ).with_for_update(of=Usuario))
            for usuario in result.scalars():
                rut = normalizar_rut(usuario.username)
                if rut in usuarios:
                    raise ConflictException("Existen cuentas duplicadas para un mismo RUT; revisar antes de sincronizar.")
                usuarios[rut] = usuario
        return usuarios

    async def guardar(self, db: AsyncSession, registro: ConductorSync) -> None:
        db.add(registro)
        await db.commit()


conductor_sync_repository = ConductorSyncRepository()
