from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.repository.user_repository import user_repository

SessionDep = Depends(get_db)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False
)


async def get_current_user(
    db: AsyncSession = SessionDep,
    token: Optional[str] = Depends(reusable_oauth2),
) -> Optional[Usuario]:
    """
    Extrae y valida el token JWT del encabezado Authorization: Bearer <token>.
    Devuelve el modelo Usuario autenticado si es válido.
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

    user = await user_repository.get_by_id(db, user_id=user_id)
    if not user or not user.is_active:
        return None
    return user


async def require_current_user(
    user: Optional[Usuario] = Depends(get_current_user),
) -> Usuario:
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
    current_user: Usuario = Depends(require_current_user),
) -> Usuario:
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
    current_user: Usuario = Depends(require_current_user),
) -> Usuario:
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
    current_user: Usuario = Depends(require_current_user),
) -> Usuario:
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

