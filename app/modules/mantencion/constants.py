from enum import Enum
from typing import Final


class EstadoSolicitud(str, Enum):
    """Estados canónicos del ciclo de vida de una Solicitud de Mantención en Taller."""
    REPORTADO = "REPORTADO"
    EN_REPARACION = "EN_REPARACION"
    PENDIENTE = "PENDIENTE"
    PENDIENTE_REASIGNACION = "PENDIENTE_REASIGNACION"
    FINALIZADO = "FINALIZADO"


class OrigenAsignacion(str, Enum):
    """Origen de asignación de mecánicos a averías."""
    SUPERVISOR = "SUPERVISOR"
    AUTOASIGNACION = "AUTOASIGNACION"
    MECANICO = "MECANICO"


class TipoComentarioBitacora(str, Enum):
    """Tipos de comentarios registrados en la bitácora inmutable de la solicitud."""
    GENERAL = "GENERAL"
    AVANCE = "AVANCE"
    CIERRE = "CIERRE"
    SISTEMA = "SISTEMA"


class EstadoItemPauta(str, Enum):
    """Estados posibles para las respuestas de los ítems de la pauta preventiva."""
    OK = "OK"
    DEFECTO = "DEFECTO"
    NO_APLICA = "NO_APLICA"


# Cantidad canónica de ítems en el catálogo maestro de pauta preventiva de taller
TOTAL_ITEMS_PAUTA_PREVENTIVA: Final[int] = 11

# Parámetros estándar de paginación para consultas de listados de solicitudes
DEFAULT_PAGE_SKIP: Final[int] = 0
DEFAULT_PAGE_LIMIT: Final[int] = 50
MAX_PAGE_LIMIT: Final[int] = 100
