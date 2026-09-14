import time
from typing import Dict, Optional, Tuple

from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO

# Caché en memoria de usuarios autenticados: {user_id: (timestamp_monotonic, UsuarioResponseDTO)}
_USER_CACHE: Dict[int, Tuple[float, UsuarioResponseDTO]] = {}
_USER_CACHE_TTL_SECONDS: float = 300.0  # 5 minutos de TTL


def get_cached_user(user_id: int) -> Optional[UsuarioResponseDTO]:
    """Recupera un usuario de la caché si no ha expirado y sigue activo."""
    now = time.monotonic()
    if user_id in _USER_CACHE:
        cached_time, cached_user = _USER_CACHE[user_id]
        if (now - cached_time) < _USER_CACHE_TTL_SECONDS and cached_user.is_active:
            return cached_user
    return None


def set_cached_user(user_id: int, user_dto: UsuarioResponseDTO) -> None:
    """Guarda un usuario en la caché en memoria con marca de tiempo actual."""
    _USER_CACHE[user_id] = (time.monotonic(), user_dto)


def clear_user_cache(user_id: Optional[int] = None) -> None:
    """Invalida la caché de usuarios. Si se especifica user_id, invalida solo ese usuario."""
    if user_id is not None:
        _USER_CACHE.pop(user_id, None)
    else:
        _USER_CACHE.clear()
