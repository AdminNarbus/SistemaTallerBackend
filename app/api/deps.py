import time
from typing import Optional, Dict, Tuple
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.auth.repository.user_repository import user_repository

SessionDep = Depends(get_db)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False
)

_USER_CACHE: Dict[int, Tuple[float, UsuarioResponseDTO]] = {}
_USER_CACHE_TTL_SECONDS: float = 300.0  # 5 minutos de TTL para mantener sesiones activas sin reconsultar a la nube


def clear_user_cache() -> None:
    """Invalida la caché en memoria de usuarios autenticados."""
    _USER_CACHE.clear()


async def get_current_user(
    db: AsyncSession = SessionDep,
    token: Optional[str] = Depends(reusable_oauth2),
) -> Optional[UsuarioResponseDTO]:
    """
    Extrae y valida el token JWT del encabezado Authorization: Bearer <token>.
    Devuelve el DTO UsuarioResponseDTO autenticado si es válido, utilizando una caché ligera en memoria
    para evitar consultas redundantes a la base de datos en ráfagas de peticiones.
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

    now = time.monotonic()
    if user_id in _USER_CACHE:
        cached_time, cached_user = _USER_CACHE[user_id]
        if (now - cached_time) < _USER_CACHE_TTL_SECONDS and cached_user.is_active:
            return cached_user

    user = await user_repository.get_by_id(db, user_id=user_id)
    if not user or not user.is_active:
        _USER_CACHE.pop(user_id, None)
        return None

    user_dto = UsuarioResponseDTO.model_validate(user)
    _USER_CACHE[user_id] = (now, user_dto)
    return user_dto


async def require_current_user(
    user: Optional[UsuarioResponseDTO] = Depends(get_current_user),
) -> UsuarioResponseDTO:
    """
    Dependencia estricta que exige estar autenticado; de lo contrario lanza HTTP 401.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de autenticación no válidas o sesión expirada",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_supervisor_or_admin(
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> UsuarioResponseDTO:
    """
    Exige que el usuario autenticado sea SUPERVISOR o ADMIN; de lo contrario lanza HTTP 403 Forbidden.
    """
    rol_upper = (current_user.rol or "").upper().strip()
    if rol_upper not in ["SUPERVISOR", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: Se requieren permisos de SUPERVISOR o ADMIN.",
        )
    return current_user


async def require_mecanico_or_admin(
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> UsuarioResponseDTO:
    """
    Exige que el usuario autenticado sea MECÁNICO o ADMIN; de lo contrario lanza HTTP 403 Forbidden.
    """
    rol_upper = (current_user.rol or "").upper().strip()
    if rol_upper not in ["MECANICO", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: Se requieren permisos de MECÁNICO o ADMIN.",
        )
    return current_user


async def require_conductor_or_admin(
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> UsuarioResponseDTO:
    """
    Exige que el usuario autenticado sea CONDUCTOR o ADMIN; de lo contrario lanza HTTP 403 Forbidden.
    """
    rol_upper = (current_user.rol or "").upper().strip()
    if rol_upper not in ["CONDUCTOR", "ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: Se requieren permisos de CONDUCTOR o ADMIN.",
        )
    return current_user

