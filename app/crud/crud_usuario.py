from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate


async def get_usuario_by_username(
    db: AsyncSession, username: str
) -> Optional[Usuario]:
    """Busca un usuario en la BD por su nombre de usuario (case-insensitive)."""
    stmt = select(Usuario).where(Usuario.username.ilike(username.strip()))
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_usuario_by_id(
    db: AsyncSession, user_id: int
) -> Optional[Usuario]:
    """Busca un usuario por su ID de clave primaria."""
    stmt = select(Usuario).where(Usuario.id == user_id)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def crear_usuario(
    db: AsyncSession, usuario_in: UsuarioCreate
) -> Usuario:
    """Crea un nuevo usuario en la BD encriptando su contraseña con bcrypt."""
    password_hash = get_password_hash(usuario_in.password)
    db_usuario = Usuario(
        username=usuario_in.username.strip(),
        password_hash=password_hash,
        rol=usuario_in.rol or "CONDUCTOR",
        conductor_id=usuario_in.conductor_id,
        is_active=usuario_in.is_active if usuario_in.is_active is not None else True,
    )
    db.add(db_usuario)
    await db.commit()
    await db.refresh(db_usuario)
    return db_usuario


async def autenticar_usuario(
    db: AsyncSession, username: str, password: str
) -> Optional[Usuario]:
    """Valida las credenciales ingresadas (username + password) contra el hash guardado."""
    user = await get_usuario_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
