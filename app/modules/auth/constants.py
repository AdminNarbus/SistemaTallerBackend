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

DEFAULT_PAGE_SKIP: Final[int] = 0
DEFAULT_PAGE_LIMIT: Final[int] = 20
MAX_PAGE_LIMIT: Final[int] = 100
