from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.crud.crud_usuario import get_usuario_by_id
from app.models.usuario import Usuario

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

    user = await get_usuario_by_id(db, user_id=user_id)
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
