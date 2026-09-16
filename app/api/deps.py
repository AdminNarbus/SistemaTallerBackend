from typing import Optional
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationException, PermissionException
from app.modules.auth.constants import RolUsuario
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.auth.services.auth_service import auth_service
from app.modules.auth.user_cache import (
    _USER_CACHE,
    _USER_CACHE_TTL_SECONDS,
    clear_user_cache,
)

SessionDep = Depends(get_db)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False
)


async def get_current_user(
    db: AsyncSession = SessionDep,
    token: Optional[str] = Depends(reusable_oauth2),
) -> Optional[UsuarioResponseDTO]:
    """
    Extrae y valida el token JWT del encabezado Authorization: Bearer <token>.
    Delega la resolución y caché del perfil a AuthService.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None
        user_id = int(user_id_str)
    except Exception:
        return None

    return await auth_service.get_current_user_profile(db, user_id=user_id)


async def require_current_user(
    user: Optional[UsuarioResponseDTO] = Depends(get_current_user),
) -> UsuarioResponseDTO:
    """Dependencia estricta que exige usuario autenticado; lanza AuthenticationException (401)."""
    if not user:
        raise AuthenticationException(
            "Credenciales de autenticación no válidas o sesión expirada"
        )
    return user


async def require_supervisor_or_admin(
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> UsuarioResponseDTO:
    """Exige que el usuario autenticado sea SUPERVISOR o ADMIN; lanza PermissionException (403)."""
    rol_upper = (current_user.rol or "").upper().strip()
    if rol_upper not in [RolUsuario.SUPERVISOR.value, RolUsuario.ADMIN.value]:
        raise PermissionException(
            "Acceso denegado: Se requieren permisos de SUPERVISOR o ADMIN."
        )
    return current_user


async def require_mecanico_or_admin(
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> UsuarioResponseDTO:
    """Exige que el usuario autenticado sea MECÁNICO o ADMIN; lanza PermissionException (403)."""
    rol_upper = (current_user.rol or "").upper().strip()
    if rol_upper not in [RolUsuario.MECANICO.value, RolUsuario.ADMIN.value]:
        raise PermissionException(
            "Acceso denegado: Se requieren permisos de MECÁNICO o ADMIN."
        )
    return current_user


async def require_conductor_or_admin(
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> UsuarioResponseDTO:
    """Exige que el usuario autenticado sea CONDUCTOR o ADMIN; lanza PermissionException (403)."""
    rol_upper = (current_user.rol or "").upper().strip()
    if rol_upper not in [RolUsuario.CONDUCTOR.value, RolUsuario.ADMIN.value]:
        raise PermissionException(
            "Acceso denegado: Se requieren permisos de CONDUCTOR o ADMIN."
        )
    return current_user


async def require_conductor_or_supervisor_or_admin(
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> UsuarioResponseDTO:
    """Exige que el usuario autenticado sea CONDUCTOR, SUPERVISOR o ADMIN; lanza PermissionException (403)."""
    rol_upper = (current_user.rol or "").upper().strip()
    if rol_upper not in [
        RolUsuario.CONDUCTOR.value,
        RolUsuario.SUPERVISOR.value,
        RolUsuario.ADMIN.value,
    ]:
        raise PermissionException(
            "Acceso denegado: Se requieren permisos de CONDUCTOR, SUPERVISOR o ADMIN."
        )
    return current_user


async def require_mecanico_or_supervisor_or_admin(
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> UsuarioResponseDTO:
    """Exige que el usuario autenticado sea MECÁNICO, SUPERVISOR o ADMIN; lanza PermissionException (403)."""
    rol_upper = (current_user.rol or "").upper().strip()
    if rol_upper not in [
        RolUsuario.MECANICO.value,
        RolUsuario.SUPERVISOR.value,
        RolUsuario.ADMIN.value,
    ]:
        raise PermissionException(
            "Acceso denegado: Se requieren permisos de MECÁNICO, SUPERVISOR o ADMIN."
        )
    return current_user

