from enum import StrEnum
from typing import Final


class TipoAlertaSupervision(StrEnum):
    """Tipos canónicos de alertas operacionales de taller."""

    REPUESTO_FALTANTE = "REPUESTO_FALTANTE"
    DEFECTO_PAUTA = "DEFECTO_PAUTA"
    BUS_SIN_MECANICOS = "BUS_SIN_MECANICOS"
    TIEMPO_EXCEDIDO = "TIEMPO_EXCEDIDO"


class SeveridadAlerta(StrEnum):
    """Niveles de severidad de alertas operacionales de supervisión."""

    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


DEFAULT_PAGE_SKIP: Final[int] = 0
DEFAULT_PAGE_LIMIT: Final[int] = 50
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
