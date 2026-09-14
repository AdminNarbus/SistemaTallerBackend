import logging
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationException,
    BusinessRuleException,
    ConflictException,
    NotFoundException,
)
from app.core.security import create_access_token, get_password_hash, verify_password
from app.modules.auth.constants import (
    DEFAULT_PAGE_LIMIT,
    ROLES_PERMITIDOS,
    RolUsuario,
)
from app.modules.auth.dtos import (
    TokenDTO,
    UsuarioCreateDTO,
    UsuarioLoginDTO,
    UsuarioResponseDTO,
)
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.repository.user_repository import user_repository
from app.modules.auth.user_cache import (
    clear_user_cache,
    get_cached_user,
    set_cached_user,
)

logger = logging.getLogger(__name__)


class AuthService:
    """
    Capa de servicio de negocio para autenticación, generación de tokens y gestión de cuentas de usuario.
    Independiente de la capa de transporte/HTTP (FastAPI).
    """

    async def login(self, db: AsyncSession, login_data: UsuarioLoginDTO) -> TokenDTO:
        """Caso de Uso: Autenticación de credenciales de usuario y emisión de Token JWT Bearer."""
        logger.info("[AUTH] Intento de login | username='%s'", login_data.username)
        user = await user_repository.get_by_username(db, username=login_data.username)
        if not user or not verify_password(login_data.password, user.password_hash):
            logger.warning("[AUTH] Credenciales inválidas para usuario: '%s'", login_data.username)
            raise AuthenticationException("Usuario o contraseña incorrectos.")

        if not user.is_active:
            logger.warning("[AUTH] Intento de login con usuario inactivo: '%s'", login_data.username)
            raise BusinessRuleException("El usuario se encuentra inactivo.")

        access_token = create_access_token(subject=user.id)
        user_dto = UsuarioResponseDTO.model_validate(user)
        set_cached_user(user.id, user_dto)
        logger.info("[AUTH] Token JWT emitido exitosamente | id=%s | username='%s'", user.id, user.username)

        return TokenDTO(access_token=access_token, token_type="bearer", user=user_dto)

    async def login_access_token(
        self, db: AsyncSession, form_data: Any
    ) -> TokenDTO:
        """Adaptador de conveniencia para solicitudes con OAuth2 Password Request Form."""
        login_dto = UsuarioLoginDTO(
            username=form_data.username, password=form_data.password
        )
        return await self.login(db, login_data=login_dto)

    async def _validar_y_resolver_rol(
        self, db: AsyncSession, rol_solicitado: Optional[Any]
    ) -> Rol:
        """Valida pertenencia a RolUsuario y existencia en base de datos."""
        rol_nombre = getattr(rol_solicitado, "value", rol_solicitado) or RolUsuario.CONDUCTOR.value
        rol_str = str(rol_nombre).upper().strip()

        if rol_str not in ROLES_PERMITIDOS:
            raise BusinessRuleException(f"El rol '{rol_solicitado}' no es válido.")

        rol_obj = await user_repository.get_rol_by_nombre(db, rol_str)
        if not rol_obj:
            # Si el rol es legítimo de RolUsuario pero aún no ha sido sembrado en la BD (ej. pruebas en memoria),
            # se inicializa de forma segura bajo el catálogo permitido.
            rol_obj = Rol(nombre=rol_str, descripcion=f"Rol de {rol_str.capitalize()}")
            db.add(rol_obj)
            await db.flush()
        return rol_obj

    async def _crear_usuario_entidad(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> Usuario:
        """Valida unicidad, resuelve rol, hashea contraseña y persiste la entidad Usuario."""
        user_existente = await user_repository.get_by_username(
            db, username=usuario_in.username
        )
        if user_existente:
            raise ConflictException("El nombre de usuario ya está registrado en el sistema.")

        rol_obj = await self._validar_y_resolver_rol(db, usuario_in.rol)
        password_hash = get_password_hash(usuario_in.password)

        nuevo_usuario = Usuario(
            nombre=usuario_in.nombre,
            apellido=usuario_in.apellido,
            username=usuario_in.username.strip(),
            password_hash=password_hash,
            rol_id=rol_obj.id,
            is_active=usuario_in.is_active if usuario_in.is_active is not None else True,
        )
        nuevo_usuario.rol_rel = rol_obj
        await user_repository.create(db, nuevo_usuario)
        await db.commit()
        return nuevo_usuario

    async def register(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> TokenDTO:
        """Caso de Uso: Auto-registro de un nuevo usuario en la plataforma."""
        logger.info("[AUTH] Solicitud de registro | username='%s' | rol='%s'", usuario_in.username, usuario_in.rol)
        nuevo_usuario = await self._crear_usuario_entidad(db, usuario_in)
        access_token = create_access_token(subject=nuevo_usuario.id)
        user_dto = UsuarioResponseDTO.model_validate(nuevo_usuario)
        set_cached_user(nuevo_usuario.id, user_dto)
        logger.info("[AUTH] Registro exitoso | id=%s | username='%s'", nuevo_usuario.id, nuevo_usuario.username)

        return TokenDTO(access_token=access_token, token_type="bearer", user=user_dto)

    async def crear_usuario(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> UsuarioResponseDTO:
        """Caso de Uso: Creación administrativa de usuario (desde panel de supervisor o admin)."""
        logger.info("[AUTH] Creación administrativa de usuario | username='%s' | rol='%s'", usuario_in.username, usuario_in.rol)
        nuevo_usuario = await self._crear_usuario_entidad(db, usuario_in)
        logger.info("[AUTH] Usuario administrativo creado | id=%s | username='%s'", nuevo_usuario.id, nuevo_usuario.username)
        return UsuarioResponseDTO.model_validate(nuevo_usuario)

    async def deshabilitar_usuario(
        self, db: AsyncSession, usuario_id: int, current_user_id: int
    ) -> UsuarioResponseDTO:
        """Caso de Uso: Deshabilita la cuenta de un usuario (soft-delete)."""
        logger.info("[AUTH] Deshabilitando usuario | id=%s | solicitado_por=%s", usuario_id, current_user_id)
        if current_user_id == usuario_id:
            raise BusinessRuleException(
                "No puedes deshabilitar tu propia cuenta de usuario.", status_code=400
            )

        user = await user_repository.get_by_id(db, user_id=usuario_id)
        if not user:
            raise NotFoundException("El usuario especificado no fue encontrado.")

        await user_repository.desactivar(db, user)
        await db.commit()
        clear_user_cache(usuario_id)
        return UsuarioResponseDTO.model_validate(user)

    async def get_current_user_profile(
        self, db: AsyncSession, user_id: int
    ) -> Optional[UsuarioResponseDTO]:
        """Obtiene el perfil de usuario autenticado por su ID, aplicando caché en memoria."""
        cached_user = get_cached_user(user_id)
        if cached_user:
            return cached_user

        user = await user_repository.get_by_id(db, user_id=user_id)
        if not user or not user.is_active:
            clear_user_cache(user_id)
            return None

        user_dto = UsuarioResponseDTO.model_validate(user)
        set_cached_user(user_id, user_dto)
        return user_dto

    async def listar_usuarios(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[UsuarioResponseDTO]:
        """Lista todos los usuarios registrados con soporte de paginación."""
        usuarios = await user_repository.get_all(db, skip=skip, limit=limit)
        return [UsuarioResponseDTO.model_validate(u) for u in usuarios]

    async def buscar_mecanicos(
        self,
        db: AsyncSession,
        q: Optional[str] = None,
        exclude_id: Optional[int] = None,
        skip: int = 0,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> List[UsuarioResponseDTO]:
        """Busca mecánicos activos con paginación y filtros opcionales."""
        mecanicos = await user_repository.buscar_mecanicos(
            db, q=q, exclude_id=exclude_id, skip=skip, limit=limit
        )
        return [UsuarioResponseDTO.model_validate(m) for m in mecanicos]


auth_service = AuthService()
