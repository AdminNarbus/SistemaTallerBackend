from app.modules.dashboard.dtos.buses_dto import BusIdentityDTO
from app.modules.dashboard.dtos.common import DTO, UtcDatetime


class MilestoneDTO(DTO):
    hito_id: str
    solicitud_id: int
    tipo_evento: str
    fecha_evento: UtcDatetime
    estado_anterior: str | None
    estado_nuevo: str
    derivado: bool
    creador_nombre: str | None


class HistoricalFaultDTO(DTO):
    solicitud_id: int
    hito_id: str
    tipo_evento: str
    fecha_evento: UtcDatetime
    estado_ot: str
    creador_nombre: str | None
    detalle_id: int | None
    descripcion: str | None
    fecha_reporte: UtcDatetime | None
    reportante_nombre: str | None
    estado_falla: str | None
    mecanicos_nombres: list[str]


class TimelineSummaryDTO(DTO):
    bus: BusIdentityDTO
    estado_actual: str | None
    ot_distintas: int
    solicitudes_distintas: int
    fallas_distintas: int
    resueltas: int
    pendientes: int
    incompletas: int
    sin_estado_documentado: int
