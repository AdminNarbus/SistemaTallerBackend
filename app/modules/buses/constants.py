from typing import Final

# Rango numérico de máquinas asignadas a la flota operativa de taller (transporte de pasajeros)
# Buses fuera de este rango (ej. servicios auxiliares < 200 o especiales >= 900) se excluyen del catálogo de taller.
RANGO_MIN_BUS_OPERATIVO: Final[int] = 200
RANGO_MAX_BUS_OPERATIVO: Final[int] = 900

# Parámetros canónicos de paginación para colecciones de buses
DEFAULT_PAGE_SKIP: Final[int] = 0
DEFAULT_PAGE_LIMIT: Final[int] = 20
MAX_PAGE_LIMIT: Final[int] = 100
