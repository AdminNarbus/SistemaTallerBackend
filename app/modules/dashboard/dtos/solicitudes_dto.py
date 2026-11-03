from app.modules.dashboard.dtos.common import DTO, UtcDatetime


class OrderDTO(DTO):
    id: int
    bus_id: int | None
    n_bus: str
    estado: str
    es_ot: bool
    total_fallas: int
    fecha_creacion: UtcDatetime
    fecha_creacion_ot: UtcDatetime | None
    fecha_termino: UtcDatetime | None
    completo_horas: float | None
