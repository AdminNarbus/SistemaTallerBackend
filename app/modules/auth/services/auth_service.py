import logging
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationException,
    BusinessRuleException,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
)
from app.modules.auth.dtos import (
    TokenDTO,
    UsuarioCreateDTO,
    UsuarioLoginDTO,
    UsuarioResponseDTO,
)
from app.modules.auth.repository.user_repository import user_repository
from app.modules.auth.user_cache import set_cached_user
from app.modules.auth.services.user_service import user_service
from app.modules.auth.services.mechanic_service import mechanic_service

logger = logging.getLogger(__name__)


class AuthService:
    """
    Capa de servicio de negocio especializada en autenticación de credenciales,
    emisión de tokens JWT Bearer y control de sesiones activas.
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
        refresh_token = create_refresh_token(subject=user.id)
        user_dto = UsuarioResponseDTO.model_validate(user)
        set_cached_user(user.id, user_dto)
        logger.info("[AUTH] Token JWT emitido exitosamente | id=%s | username='%s'", user.id, user.username)

        return TokenDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user_dto,
        )

    async def refresh(self, db: AsyncSession, refresh_token: str) -> TokenDTO:
        """Rota un refresh token válido por un nuevo par de tokens."""
        try:
            user_id = decode_refresh_token(refresh_token)
        except ValueError as exc:
            raise AuthenticationException("Refresh token inválido o expirado.") from exc

        user = await user_repository.get_by_id(db, user_id=user_id)
        if not user or not user.is_active:
            raise AuthenticationException("La sesión no es válida para este usuario.")

        user_dto = UsuarioResponseDTO.model_validate(user)
        set_cached_user(user.id, user_dto)
        return TokenDTO(
            access_token=create_access_token(subject=user.id),
            refresh_token=create_refresh_token(subject=user.id),
            token_type="bearer",
            user=user_dto,
        )

    async def login_access_token(
        self, db: AsyncSession, form_data: Any
    ) -> TokenDTO:
        """Adaptador de conveniencia para solicitudes con OAuth2 Password Request Form."""
        login_dto = UsuarioLoginDTO(
            username=form_data.username, password=form_data.password
        )
        return await self.login(db, login_data=login_dto)

    # -------------------------------------------------------------------------
    # Delegaciones de conveniencia / Fachada hacia UserService y MechanicService
    # (Garantizan retrocompatibilidad absoluta sin romper otros módulos)
    # -------------------------------------------------------------------------

    async def register(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> TokenDTO:
        return await user_service.register(db, usuario_in=usuario_in)

    async def crear_usuario(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> UsuarioResponseDTO:
        return await user_service.crear_usuario(db, usuario_in=usuario_in)

    async def deshabilitar_usuario(
        self, db: AsyncSession, usuario_id: int, current_user_id: int
    ) -> UsuarioResponseDTO:
        return await user_service.deshabilitar_usuario(
            db, usuario_id=usuario_id, current_user_id=current_user_id
        )

    async def get_current_user_profile(
        self, db: AsyncSession, user_id: int
    ) -> Optional[UsuarioResponseDTO]:
        return await user_service.get_current_user_profile(db, user_id=user_id)

    async def listar_usuarios(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        rol: Optional[str] = None,
        q: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[UsuarioResponseDTO]:
        return await user_service.listar_usuarios(
            db, skip=skip, limit=limit, rol=rol, q=q, is_active=is_active
        )

    async def contar_usuarios(
        self,
        db: AsyncSession,
        rol: Optional[str] = None,
        q: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> int:
        return await user_service.contar_usuarios(
            db, rol=rol, q=q, is_active=is_active
        )

    async def buscar_mecanicos(
        self,
        db: AsyncSession,
        q: Optional[str] = None,
        exclude_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[UsuarioResponseDTO]:
        return await mechanic_service.buscar_mecanicos(
            db, q=q, exclude_id=exclude_id, skip=skip, limit=limit
        )

    async def contar_mecanicos(
        self,
        db: AsyncSession,
        q: Optional[str] = None,
        exclude_id: Optional[int] = None,
    ) -> int:
        return await mechanic_service.contar_mecanicos(
            db, q=q, exclude_id=exclude_id
        )


auth_service = AuthService()

__all__ = ["AuthService", "auth_service"]
