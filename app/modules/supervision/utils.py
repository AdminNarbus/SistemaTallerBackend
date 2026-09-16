from typing import Optional, TYPE_CHECKING
from app.modules.supervision.constants import (
    TipoAlertaSupervision,
    SeveridadAlerta,
    BUS_SIN_NUMERO,
)

if TYPE_CHECKING:
    from app.modules.supervision.dtos.supervision_dto import AlertaSupervisionDTO


def calcular_porcentaje_resolucion(total_fallas: int, total_resueltas: int) -> float:
    """
    Calcula el porcentaje de fallas resueltas de manera pura y segura contra división por cero.
    Retorna float redondeado a 2 decimales.
    """
    if total_fallas <= 0 or total_resueltas <= 0:
        return 0.0
    return round((total_resueltas / total_fallas) * 100.0, 2)


def formatear_mensaje_alerta_repuesto(
    detalle_id: Optional[int],
    n_bus: str,
    comentario_repuesto: Optional[str] = None,
) -> str:
    """Construye el mensaje legible para alertas de fallas detenidas por repuestos."""
    bus_label = n_bus or BUS_SIN_NUMERO
    base = f"Falla #{detalle_id} en Bus {bus_label} detenida por falta de repuestos"
    if comentario_repuesto and comentario_repuesto.strip():
        return f"{base}: {comentario_repuesto.strip()}"
    return base


def formatear_mensaje_alerta_pauta(
    n_bus: str,
    item_nombre: Optional[str] = None,
    item_id: Optional[int] = None,
) -> str:
    """Construye el mensaje para alertas de ítems de pauta preventiva con defecto."""
    bus_label = n_bus or BUS_SIN_NUMERO
    item_txt = item_nombre if item_nombre and item_nombre.strip() else f"Ítem #{item_id}"
    return f"Ítem de pauta preventiva con defecto en Bus {bus_label}: {item_txt}"


def formatear_mensaje_alerta_bus_sin_mecanicos(n_bus: str) -> str:
    """Construye el mensaje para alertas de buses en reparación sin mecánicos asignados."""
    bus_label = n_bus or BUS_SIN_NUMERO
    return f"Bus {bus_label} figura EN_REPARACION pero no tiene mecánicos activos asignados"


def construir_alerta_supervision(
    tipo: TipoAlertaSupervision | str,
    severidad: SeveridadAlerta | str,
    solicitud_id: int,
    n_bus: Optional[str],
    mensaje: str,
    detalle_id: Optional[int] = None,
) -> "AlertaSupervisionDTO":
    """Helper constructor puro para instanciar AlertaSupervisionDTO."""
    from app.modules.supervision.dtos.supervision_dto import AlertaSupervisionDTO

    return AlertaSupervisionDTO(
        tipo=tipo,
        severidad=severidad,
        solicitud_id=solicitud_id,
        n_bus=n_bus or BUS_SIN_NUMERO,
        mensaje=mensaje,
        detalle_id=detalle_id,
    )


def formatear_comentario_cambio_estado(
    supervisor_nombre: str,
    estado_anterior: str,
    nuevo_estado: str,
    motivo: Optional[str] = None,
) -> str:
    """Construye el texto descriptivo canónico para la bitácora inmutable al cambiar el estado de una OT."""
    base = f"Supervisora {supervisor_nombre} cambió el estado de {estado_anterior} a {nuevo_estado}"
    if motivo and motivo.strip():
        return f"{base}. Motivo: {motivo.strip()}"
    return f"{base}."

