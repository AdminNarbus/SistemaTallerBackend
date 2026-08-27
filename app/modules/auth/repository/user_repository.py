from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.modules.auth.dtos.usuario_dto import UsuarioCreateDTO
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario


class UserRepository:
    """Repositorio para la gestión de persistencia y consultas de usuarios y roles."""

    async def get_or_create_rol(self, db: AsyncSession, nombre_rol: str) -> Rol:
        """Busca o crea un rol en la tabla roles."""
        rol_clean = (nombre_rol or "CONDUCTOR").upper().strip()
        stmt = select(Rol).where(Rol.nombre == rol_clean)
        res = await db.execute(stmt)
        rol = res.scalar_one_or_none()
        if not rol:
            rol = Rol(nombre=rol_clean, descripcion=f"Rol de {rol_clean.capitalize()}")
            db.add(rol)
            await db.commit()
            await db.refresh(rol)
        return rol

    async def get_by_username(
        self, db: AsyncSession, username: str
    ) -> Optional[Usuario]:
        """Busca un usuario por su username (case-insensitive)."""
        stmt = select(Usuario).where(Usuario.username.ilike(username.strip()))
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_id(
        self, db: AsyncSession, user_id: int
    ) -> Optional[Usuario]:
        """Busca un usuario por su ID de clave primaria."""
        stmt = select(Usuario).where(Usuario.id == user_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_all(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[Usuario]:
        """Lista todos los usuarios registrados."""
        stmt = select(Usuario).order_by(Usuario.id.asc()).offset(skip).limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def create(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> Usuario:
        """Crea un nuevo usuario en la BD encriptando su contraseña y vinculando su rol_id."""
        rol_obj = await self.get_or_create_rol(db, usuario_in.rol or "CONDUCTOR")
        password_hash = get_password_hash(usuario_in.password)
        db_usuario = Usuario(
            nombre=usuario_in.nombre,
            apellido=usuario_in.apellido,
            username=usuario_in.username.strip(),
            password_hash=password_hash,
            rol_id=rol_obj.id,
            is_active=usuario_in.is_active if usuario_in.is_active is not None else True,
        )
        db.add(db_usuario)
        await db.commit()
        await db.refresh(db_usuario)
        return db_usuario

    async def desactivar(
        self, db: AsyncSession, user_id: int
    ) -> Optional[Usuario]:
        """Soft-delete: Deshabilita la cuenta estableciendo is_active = False."""
        user = await self.get_by_id(db, user_id=user_id)
        if not user:
            return None

        user.is_active = False
        await db.commit()
        await db.refresh(user)
        return user

    async def authenticate(
        self, db: AsyncSession, username: str, password: str
    ) -> Optional[Usuario]:
        """Valida credenciales ingresadas contra el hash guardado."""
        user = await self.get_by_username(db, username)
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user


user_repository = UserRepository()
