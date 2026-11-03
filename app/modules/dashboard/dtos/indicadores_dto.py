from app.modules.dashboard.dtos.common import DTO


class StateMetricsDTO(DTO):
    total_ot: int
    solicitadas_buses: int
    pendientes_buses: int
    en_reparacion_buses: int
    liberados_buses: int
    finalizadas_ot: int
    reportadas_ot: int


class DurationDTO(DTO):
    promedio_horas: float | None
    mediana_horas: float | None
    validos: int
    sin_datos: int
    invalidos: int


class DurationsDTO(DTO):
    respuesta: DurationDTO
    reparacion: DurationDTO
    completo: DurationDTO


class MonthlyDTO(DTO):
    periodo: str | None
    ot_atendidas: int
    ot_totales: int
    porcentaje_ot_atendidas: float | None
    fallas_atendidas: int
    fallas_reportadas: int
    porcentaje_fallas_atendidas: float | None
    reincidencias: int


class IndicatorsDTO(DTO):
    estados: StateMetricsDTO
    tiempos: DurationsDTO
    mensuales: MonthlyDTO
