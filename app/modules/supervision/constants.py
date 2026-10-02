from enum import StrEnum
from typing import Final


class TipoAlertaSupervision(StrEnum):
    """Tipos canónicos de alertas operacionales de taller."""

    OT_SIN_INGRESO_TALLER = "OT_SIN_INGRESO_TALLER"
    LIBERADO_TIEMPO_EXCEDIDO = "LIBERADO_TIEMPO_EXCEDIDO"


class SeveridadAlerta(StrEnum):
    """Niveles de severidad de alertas operacionales de supervisión."""

    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


DEFAULT_PAGE_SKIP: Final[int] = 0
DEFAULT_PAGE_LIMIT: Final[int] = 20
MAX_PAGE_LIMIT: Final[int] = 100

BUS_SIN_NUMERO: Final[str] = "S/N"
CATEGORIA_SIN_ASIGNAR_NOMBRE: Final[str] = "Personalizada / Sin Categoría"

ESTADOS_VALIDOS_AUDITORIA: Final[tuple[str, ...]] = (
    "REPORTADO",
    "PENDIENTE",
    "EN_REPARACION",
    "LIBERADO",
    "FINALIZADO",
)
