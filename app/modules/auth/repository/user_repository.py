import logging
from typing import Any, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

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
            await db.flush()
        return rol

    async def get_by_username(
        self, db: AsyncSession, username: str
    ) -> Optional[Usuario]:
        """Busca un usuario por su username (case-insensitive) con su rol en un solo JOIN."""
        logger.debug("[AUTH] Buscando usuario por username='%s'", username.strip())
        stmt = (
            select(Usuario)
            .options(joinedload(Usuario.rol_rel))
            .where(Usuario.username.ilike(username.strip()))
        )
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            logger.warning("[AUTH] Usuario no encontrado | username='%s'", username.strip())
        return user

    async def get_by_id(
        self, db: AsyncSession, user_id: int
    ) -> Optional[Usuario]:
        """Busca un usuario por su ID de clave primaria con su rol en un solo JOIN."""
        logger.debug("[AUTH] Buscando usuario por id=%s", user_id)
        stmt = (
            select(Usuario)
            .options(joinedload(Usuario.rol_rel))
            .where(Usuario.id == user_id)
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_ids(
        self, db: AsyncSession, user_ids: List[int]
    ) -> List[Usuario]:
        """Busca múltiples usuarios por sus IDs en una sola consulta SQL."""
        if not user_ids:
            return []
        stmt = (
            select(Usuario)
            .options(joinedload(Usuario.rol_rel))
            .where(Usuario.id.in_(user_ids))
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_by_ids_map(
        self, db: AsyncSession, user_ids: List[int]
    ) -> dict[int, Usuario]:
        """Busca múltiples usuarios por sus IDs y retorna un diccionario {id: Usuario}."""
        users = await self.get_by_ids(db, user_ids)
        return {u.id: u for u in users}

    async def get_all(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[Usuario]:
        """Lista todos los usuarios registrados."""
        stmt = select(Usuario).order_by(Usuario.id.asc()).offset(skip).limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_rol_by_nombre(
        self, db: AsyncSession, nombre_rol: str
    ) -> Optional[Rol]:
        """Busca un rol por su nombre en la tabla roles."""
        rol_clean = (nombre_rol or "").upper().strip()
        stmt = select(Rol).where(Rol.nombre == rol_clean)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def add(self, db: AsyncSession, usuario: Usuario) -> Usuario:
        """Agrega un usuario a la sesión y realiza flush atómico sin commit."""
        db.add(usuario)
        await db.flush()
        return usuario

    async def create(
        self, db: AsyncSession, usuario_or_dto: Any
    ) -> Usuario:
        """
        Persiste un usuario en la BD con flush atómico sin commit.
        Acepta una entidad Usuario ya configurada o un DTO UsuarioCreateDTO.
        """
        if isinstance(usuario_or_dto, Usuario):
            return await self.add(db, usuario_or_dto)

        # Soporte para UsuarioCreateDTO (retrocompatibilidad)
        logger.debug("[AUTH] Creando usuario desde DTO | username='%s' | rol='%s'", usuario_or_dto.username, getattr(usuario_or_dto, "rol", None))
        rol_obj = await self.get_or_create_rol(db, getattr(usuario_or_dto, "rol", None) or "CONDUCTOR")
        
        # En caso de venir de DTO, si la contraseña viene en texto plano se hashea; si ya viene hasheada se preserva
        pwd = getattr(usuario_or_dto, "password", "")
        if pwd.startswith("$2b$") or pwd.startswith("$2a$"):
            password_hash = pwd
        else:
            from app.core.security import get_password_hash
            password_hash = get_password_hash(pwd)

        db_usuario = Usuario(
            nombre=getattr(usuario_or_dto, "nombre", None),
            apellido=getattr(usuario_or_dto, "apellido", None),
            username=usuario_or_dto.username.strip(),
            password_hash=password_hash,
            rol_id=rol_obj.id,
            is_active=getattr(usuario_or_dto, "is_active", True) if getattr(usuario_or_dto, "is_active", None) is not None else True,
        )
        await self.add(db, db_usuario)
        logger.info("[AUTH] Usuario creado en sesión | id=%s | username='%s' | rol='%s'", db_usuario.id, db_usuario.username, rol_obj.nombre)
        return db_usuario

    async def desactivar(
        self, db: AsyncSession, user_or_id: Any
    ) -> Optional[Usuario]:
        """
        Soft-delete: Deshabilita la cuenta estableciendo is_active = False con flush atómico.
        Acepta tanto la entidad Usuario ya cargada (evitando consultas SQL duplicadas) como un user_id entero.
        """
        if isinstance(user_or_id, Usuario):
            user = user_or_id
        else:
            user = await self.get_by_id(db, user_id=int(user_or_id))
            if not user:
                logger.warning("[AUTH] Intento de desactivar usuario inexistente | id=%s", user_or_id)
                return None

        user.is_active = False
        await db.flush()
        logger.info("[AUTH] Usuario desactivado en sesión (soft-delete) | id=%s | username='%s'", user.id, user.username)
        return user

    async def authenticate(
        self, db: AsyncSession, username: str, password: str
    ) -> Optional[Usuario]:
        """
        Valida credenciales contra la BD.
        (Nota arquitectónica: La orquestación principal reside en AuthService;
        este método se mantiene por compatibilidad en tests de repositorio).
        """
        logger.debug("[AUTH] Intento de autenticación en repositorio | username='%s'", username)
        user = await self.get_by_username(db, username)
        if not user:
            logger.warning("[AUTH] Autenticación fallida: usuario no existe | username='%s'", username)
            return None
        from app.core.security import verify_password
        if not verify_password(password, user.password_hash):
            logger.warning("[AUTH] Autenticación fallida: contraseña incorrecta | username='%s'", username)
            return None
        logger.info("[AUTH] Autenticación exitosa en repositorio | id=%s | username='%s'", user.id, username)
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

        condiciones = []
        for item in nombres:
            clean = item.strip()
            if not clean:
                continue
            pattern = clean
            pattern_like = f"%{clean}%"
            condiciones.extend([
                Usuario.username.ilike(pattern),
                Usuario.nombre.ilike(pattern),
                func.concat(func.coalesce(Usuario.nombre, ''), ' ', func.coalesce(Usuario.apellido, '')).ilike(pattern),
                func.concat(func.coalesce(Usuario.nombre, ''), ' ', func.coalesce(Usuario.apellido, '')).ilike(pattern_like),
            ])

        if not condiciones:
            return []

        stmt = (
            select(Usuario)
            .join(Rol)
            .where(
                and_(
                    Usuario.is_active == True,
                    Rol.nombre == "MECANICO",
                    or_(*condiciones),
                )
            )
            .distinct()
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())


user_repository = UserRepository()
