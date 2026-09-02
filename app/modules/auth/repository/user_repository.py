import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.modules.auth.dtos.usuario_dto import UsuarioCreateDTO
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario

logger = logging.getLogger(__name__)


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
        logger.debug("[AUTH] Buscando usuario por username='%s'", username.strip())
        stmt = select(Usuario).where(Usuario.username.ilike(username.strip()))
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            logger.warning("[AUTH] Usuario no encontrado | username='%s'", username.strip())
        return user

    async def get_by_id(
        self, db: AsyncSession, user_id: int
    ) -> Optional[Usuario]:
        """Busca un usuario por su ID de clave primaria."""
        logger.debug("[AUTH] Buscando usuario por id=%s", user_id)
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
        logger.debug("[AUTH] Creando usuario | username='%s' | rol='%s'", usuario_in.username, usuario_in.rol)
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
        logger.info("[AUTH] Usuario creado exitosamente | id=%s | username='%s' | rol='%s'", db_usuario.id, db_usuario.username, rol_obj.nombre)
        return db_usuario

    async def desactivar(
        self, db: AsyncSession, user_id: int
    ) -> Optional[Usuario]:
        """Soft-delete: Deshabilita la cuenta estableciendo is_active = False."""
        user = await self.get_by_id(db, user_id=user_id)
        if not user:
            logger.warning("[AUTH] Intento de desactivar usuario inexistente | id=%s", user_id)
            return None

        user.is_active = False
        await db.commit()
        await db.refresh(user)
        logger.info("[AUTH] Usuario desactivado (soft-delete) | id=%s | username='%s'", user.id, user.username)
        return user

    async def authenticate(
        self, db: AsyncSession, username: str, password: str
    ) -> Optional[Usuario]:
        """Valida credenciales ingresadas contra el hash guardado."""
        logger.debug("[AUTH] Intento de autenticación | username='%s'", username)
        user = await self.get_by_username(db, username)
        if not user:
            logger.warning("[AUTH] Autenticación fallida: usuario no existe | username='%s'", username)
            return None
        if not verify_password(password, user.password_hash):
            logger.warning("[AUTH] Autenticación fallida: contraseña incorrecta | username='%s'", username)
            return None
        logger.info("[AUTH] Autenticación exitosa | id=%s | username='%s'", user.id, username)
        return user


    async def buscar_mecanicos(
        self, db: AsyncSession, q: Optional[str] = None, exclude_id: Optional[int] = None
    ) -> List[Usuario]:
        """
        Busca usuarios activos con rol MECÁNICO por nombre, apellido o username.
        Si q está vacío o es None, retorna todos los mecánicos activos.
        Si exclude_id se provee, ese usuario es excluido de los resultados (ej: el mecánico logueado).
        """
        from sqlalchemy import or_, and_, func
        stmt = (
            select(Usuario)
            .join(Rol)
            .where(
                and_(
                    Usuario.is_active == True,
                    Rol.nombre == "MECANICO",
                )
            )
        )
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Usuario.username.ilike(pattern),
                    Usuario.nombre.ilike(pattern),
                    Usuario.apellido.ilike(pattern),
                    func.concat(func.coalesce(Usuario.nombre, ''), ' ', func.coalesce(Usuario.apellido, '')).ilike(pattern),
                )
            )
        if exclude_id:
            stmt = stmt.where(Usuario.id != exclude_id)
        stmt = stmt.order_by(Usuario.nombre.asc(), Usuario.username.asc())
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_mecanicos_by_nombres_o_usernames(
        self, db: AsyncSession, nombres: List[str]
    ) -> List[Usuario]:
        """
        Dada una lista de nombres de usuario o nombres completos, resuelve los usuarios mecánicos correspondientes.
        """
        from sqlalchemy import or_, and_, func
        if not nombres:
            return []

        mecanicos_encontrados = []
        for item in nombres:
            clean = item.strip()
            if not clean:
                continue
            pattern = clean
            pattern_like = f"%{clean}%"
            stmt = (
                select(Usuario)
                .join(Rol)
                .where(
                    and_(
                        Usuario.is_active == True,
                        Rol.nombre == "MECANICO",
                        or_(
                            Usuario.username.ilike(pattern),
                            Usuario.nombre.ilike(pattern),
                            func.concat(func.coalesce(Usuario.nombre, ''), ' ', func.coalesce(Usuario.apellido, '')).ilike(pattern),
                            func.concat(func.coalesce(Usuario.nombre, ''), ' ', func.coalesce(Usuario.apellido, '')).ilike(pattern_like),
                        ),
                    )
                )
            )
            res = await db.execute(stmt)
            users = res.scalars().all()
            for user in users:
                if user not in mecanicos_encontrados:
                    mecanicos_encontrados.append(user)

        return mecanicos_encontrados


user_repository = UserRepository()
