from enum import Enum
from typing import Final


class RolUsuario(str, Enum):
    """Roles de usuario reconocidos y autorizados en el sistema Narbus."""
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    MECANICO = "MECANICO"
    CONDUCTOR = "CONDUCTOR"


ROLES_PERMITIDOS: Final[frozenset[str]] = frozenset(
    {rol.value for rol in RolUsuario}
)

DEFAULT_PAGE_LIMIT: Final[int] = 50
MAX_PAGE_LIMIT: Final[int] = 100
