import logging
from typing import Any, List, Optional
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.constants import RolUsuario, DEFAULT_PAGE_SKIP, DEFAULT_PAGE_LIMIT
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario

logger = logging.getLogger(__name__)


class UserRepository:
    """Repositorio para la gestión de persistencia y consultas de usuarios y roles."""

    async def get_or_create_rol(self, db: AsyncSession, nombre_rol: str) -> Rol:
        """
        [DEPRECADO] Busca o crea un rol en la tabla roles.
        Usar get_rol_by_nombre; los roles deben ser estáticos y controlados por migraciones.
        """
        rol_clean = (nombre_rol or "CONDUCTOR").upper().strip()
        rol = await self.get_rol_by_nombre(db, rol_clean)
        if not rol:
            logger.warning("[AUTH] Rol '%s' no encontrado; creándolo dinámicamente [DEPRECADO]", rol_clean)
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

    def _aplicar_filtros_usuarios(
        self,
        stmt,
        rol: Optional[str] = None,
        q: Optional[str] = None,
        is_active: Optional[bool] = None,
    ):
        """Aplica filtros comunes de rol, búsqueda por texto y estado activo a un query de Usuario."""
        if rol and rol.strip():
            stmt = stmt.join(Usuario.rol_rel).where(func.upper(Rol.nombre) == rol.upper().strip())
        if is_active is not None:
            stmt = stmt.where(Usuario.is_active == is_active)
        if q and q.strip():
            term = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Usuario.nombre).ilike(term),
                    func.lower(Usuario.apellido).ilike(term),
                    func.lower(Usuario.username).ilike(term),
                    func.concat(func.coalesce(Usuario.nombre, ""), " ", func.coalesce(Usuario.apellido, "")).ilike(term),
                )
            )
        return stmt

    async def get_all(
        self,
        db: AsyncSession,
        skip: int = DEFAULT_PAGE_SKIP,
        limit: int = DEFAULT_PAGE_LIMIT,
        rol: Optional[str] = None,
        q: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Usuario]:
        """Lista usuarios registrados con su rol aplicando paginación (default: 20) y filtros opcionales."""
        stmt = (
            select(Usuario)
            .options(joinedload(Usuario.rol_rel))
            .order_by(Usuario.id.asc())
        )
        stmt = self._aplicar_filtros_usuarios(stmt, rol=rol, q=q, is_active=is_active)
        stmt = stmt.offset(skip).limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def count_usuarios(
        self,
        db: AsyncSession,
        rol: Optional[str] = None,
        q: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> int:
        """Retorna el conteo total de usuarios registrados bajo los filtros especificados."""
        stmt = select(func.count(Usuario.id))
        stmt = self._aplicar_filtros_usuarios(stmt, rol=rol, q=q, is_active=is_active)
        res = await db.execute(stmt)
        return res.scalar() or 0

    async def get_rol_by_nombre(
        self, db: AsyncSession, nombre_rol: str
    ) -> Optional[Rol]:
        """Busca un rol por su nombre en la tabla roles."""
        rol_clean = (nombre_rol or "").upper().strip()
        stmt = select(Rol).where(Rol.nombre == rol_clean)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def add(self, db: AsyncSession, usuario: Usuario) -> Usuario:
        """Agrega un usuario a la sesión."""
        db.add(usuario)
        return usuario

    async def create(
        self, db: AsyncSession, usuario_or_dto: Any
    ) -> Usuario:
        """
        Persiste una entidad Usuario en la BD con flush atómico en sesión (sin commit).
        Acepta una entidad Usuario ya configurada o un DTO UsuarioCreateDTO por retrocompatibilidad.
        """
        if isinstance(usuario_or_dto, Usuario):
            db.add(usuario_or_dto)
            await db.flush()
            return usuario_or_dto

        logger.warning("[AUTH] Invocación de user_repository.create con DTO en lugar de entidad Usuario [DEPRECADO]")
        rol_nombre = getattr(usuario_or_dto, "rol", None)
        rol_str = getattr(rol_nombre, "value", rol_nombre) or "CONDUCTOR"
        rol_obj = await self.get_rol_by_nombre(db, rol_str)
        if not rol_obj:
            rol_obj = await self.get_or_create_rol(db, rol_str)

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
        db_usuario.rol_rel = rol_obj
        db.add(db_usuario)
        await db.flush()
        return db_usuario

    async def desactivar(
        self, db: AsyncSession, user_or_id: Any
    ) -> Optional[Usuario]:
        """Soft-delete: Deshabilita la cuenta estableciendo is_active = False con flush atómico."""
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
        [DEPRECADO] Valida credenciales contra la BD.
        Se recomienda delegar la autenticación exclusivamente a AuthService.login().
        """
        user = await self.get_by_username(db, username)
        if not user:
            return None
        from app.core.security import verify_password
        if not verify_password(password, user.password_hash):
            return None
        return user

    def _construir_filtro_mecanico_q(self, q: Optional[str]):
        """Construye condición de búsqueda para mecánicos por término q."""
        if not q or not q.strip():
            return None
        pattern = f"%{q.strip()}%"
        return or_(
            Usuario.username.ilike(pattern),
            Usuario.nombre.ilike(pattern),
            Usuario.apellido.ilike(pattern),
            func.concat(func.coalesce(Usuario.nombre, ""), " ", func.coalesce(Usuario.apellido, "")).ilike(pattern),
        )

    def _construir_stmt_mecanicos(
        self, q: Optional[str] = None, exclude_id: Optional[int] = None
    ):
        """Construye sentencia SQL base para búsqueda de mecánicos activos."""
        stmt = (
            select(Usuario)
            .options(joinedload(Usuario.rol_rel))
            .join(Rol, Usuario.rol_id == Rol.id)
            .where(
                and_(
                    Usuario.is_active == True,
                    Rol.nombre == RolUsuario.MECANICO.value,
                )
            )
        )
        filtro_q = self._construir_filtro_mecanico_q(q)
        if filtro_q is not None:
            stmt = stmt.where(filtro_q)
        if exclude_id:
            stmt = stmt.where(Usuario.id != exclude_id)
        return stmt.order_by(Usuario.nombre.asc(), Usuario.username.asc())

    async def buscar_mecanicos(
        self,
        db: AsyncSession,
        q: Optional[str] = None,
        exclude_id: Optional[int] = None,
        skip: int = DEFAULT_PAGE_SKIP,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> List[Usuario]:
        """Busca usuarios activos con rol MECÁNICO con paginación (default: 20) y filtros opcionales."""
        stmt = self._construir_stmt_mecanicos(q, exclude_id).offset(skip).limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def count_mecanicos(
        self,
        db: AsyncSession,
        q: Optional[str] = None,
        exclude_id: Optional[int] = None,
    ) -> int:
        """Retorna el conteo total de mecánicos activos bajo los filtros de búsqueda."""
        stmt = (
            select(func.count(Usuario.id))
            .join(Rol, Usuario.rol_id == Rol.id)
            .where(
                and_(
                    Usuario.is_active == True,
                    Rol.nombre == RolUsuario.MECANICO.value,
                )
            )
        )
        filtro_q = self._construir_filtro_mecanico_q(q)
        if filtro_q is not None:
            stmt = stmt.where(filtro_q)
        if exclude_id:
            stmt = stmt.where(Usuario.id != exclude_id)
        res = await db.execute(stmt)
        return res.scalar() or 0

    def _construir_condiciones_mecanicos_nombres(self, nombres: List[str]):
        """Construye condiciones OR de búsqueda para listado de nombres o usernames."""
        condiciones = []
        for item in nombres:
            clean = item.strip()
            if not clean:
                continue
            condiciones.extend([
                Usuario.username.ilike(clean),
                Usuario.nombre.ilike(clean),
                func.concat(func.coalesce(Usuario.nombre, ""), " ", func.coalesce(Usuario.apellido, "")).ilike(clean),
                func.concat(func.coalesce(Usuario.nombre, ""), " ", func.coalesce(Usuario.apellido, "")).ilike(f"%{clean}%"),
            ])
        return condiciones

    async def get_mecanicos_by_nombres_o_usernames(
        self, db: AsyncSession, nombres: List[str]
    ) -> List[Usuario]:
        """Dada una lista de nombres de usuario o nombres completos, resuelve los usuarios mecánicos correspondientes."""
        condiciones = self._construir_condiciones_mecanicos_nombres(nombres or [])
        if not condiciones:
            return []

        stmt = (
            select(Usuario)
            .options(joinedload(Usuario.rol_rel))
            .join(Rol, Usuario.rol_id == Rol.id)
            .where(
                and_(
                    Usuario.is_active == True,
                    Rol.nombre == RolUsuario.MECANICO.value,
                    or_(*condiciones),
                )
            )
            .distinct()
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())


user_repository = UserRepository()
