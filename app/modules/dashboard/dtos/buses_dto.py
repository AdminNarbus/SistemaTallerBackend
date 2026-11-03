from app.modules.dashboard.dtos.common import DTO


class BusIdentityDTO(DTO):
    id: int
    n_bus: str
    patente: str


class FaultCountsDTO(DTO):
    pendientes: int
    incompletas: int
    resueltas: int


class RecurrenceDTO(DTO):
    periodo: str | None
    cantidad: int


class BusSummaryDTO(DTO):
    bus: BusIdentityDTO
    ultima_ot_id: int | None
    estado: str | None
    visitas: int
    fallas: FaultCountsDTO
    reincidencias: RecurrenceDTO


class FaultGroupDTO(DTO):
    descripcion: str
    cantidad: int


class FaultOrderDTO(DTO):
    solicitud_id: int


class BusOptionDTO(DTO):
    bus_id: int | None
    n_bus: str
    patente: str | None


class OrderOptionDTO(DTO):
    id: int
    n_bus: str
    es_ot: bool


class MechanicOptionDTO(DTO):
    id: int
    nombre_completo: str | None
    is_active: bool


class PeriodOptionDTO(DTO):
    periodo: str
    mes: int
    anio: int
