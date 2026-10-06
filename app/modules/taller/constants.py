from enum import Enum
from typing import Final


class EstadoSolicitud(str, Enum):
    """Estados canónicos del ciclo de vida de una Solicitud de Mantención en Taller."""
    REPORTADO = "REPORTADO"
    PENDIENTE = "PENDIENTE"
    EN_REPARACION = "EN_REPARACION"
    LIBERADO = "LIBERADO"
    FINALIZADO = "FINALIZADO"


class EstadoFalla(str, Enum):
    """Estados canónicos para cada falla/avería individual de una solicitud de taller."""
    PENDIENTE = "PENDIENTE"
    INCOMPLETA = "INCOMPLETA"
    RESUELTA = "RESUELTA"


class TipoEventoFalla(str, Enum):
    """Eventos inmutables que describen el ciclo de vida de una falla."""

    REPORTADA = "REPORTADA"
    RESUELTA = "RESUELTA"
    REABIERTA = "REABIERTA"
    INCOMPLETA = "INCOMPLETA"
    FALTA_REPUESTO_ACTIVADA = "FALTA_REPUESTO_ACTIVADA"
    FALTA_REPUESTO_RETIRADA = "FALTA_REPUESTO_RETIRADA"



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
    CAMBIO_ESTADO = "CAMBIO_ESTADO"
    ASIGNACION = "ASIGNACION"
    ENTREGA_TURNO = "ENTREGA_TURNO"
    SALIDA_MECANICO = "SALIDA_MECANICO"
    RESOLUCION = "RESOLUCION"
    CHECKLIST = "CHECKLIST"
    REAPERTURA = "REAPERTURA"
    FALTA_REPUESTO = "FALTA_REPUESTO"
    REPUESTO_DISPONIBLE = "REPUESTO_DISPONIBLE"
    SUPERVISION = "SUPERVISION"



class EstadoItemPauta(str, Enum):
    """Estados posibles para las respuestas de los ítems de la pauta preventiva."""
    OK = "OK"
    DEFECTO = "DEFECTO"
    NO_APLICA = "NO_APLICA"


# Cantidad canónica de ítems en el catálogo maestro de pauta preventiva de taller
TOTAL_ITEMS_PAUTA_PREVENTIVA: Final[int] = 10

# Parámetros estándar de paginación para consultas de listados de solicitudes
DEFAULT_PAGE_SKIP: Final[int] = 0
DEFAULT_PAGE_LIMIT: Final[int] = 20
MAX_PAGE_LIMIT: Final[int] = 100
