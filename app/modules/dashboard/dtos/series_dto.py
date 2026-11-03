from typing import Literal
from app.modules.dashboard.dtos.common import DTO, PageDTO, UtcDatetime


class TrendPointDTO(DTO):
    semana: str
    creadas: int
    terminadas: int


class GroupPointDTO(DTO):
    grupo: str
    cantidad: int


class MechanicPointDTO(DTO):
    mecanico_id: int
    nombre_completo: str | None
    fallas_unicas: int


class BusPointDTO(DTO):
    bus_id: int
    n_bus: str
    cantidad: int


class WorkshopPointDTO(GroupPointDTO):
    porcentaje: float | None


class TrendSeriesDTO(PageDTO[TrendPointDTO]):
    serie: Literal["tendencia"] = "tendencia"
    periodos_aplicados: list[str]


class AgeSeriesDTO(PageDTO[GroupPointDTO]):
    serie: Literal["antiguedad"] = "antiguedad"
    periodos_aplicados: list[str]
    fecha_corte_calculo: UtcDatetime | None


class MechanicSeriesDTO(PageDTO[MechanicPointDTO]):
    serie: Literal["mecanicos"] = "mecanicos"
    periodos_aplicados: list[str]


class BusSeriesDTO(PageDTO[BusPointDTO]):
    serie: Literal["buses-fallas", "buses-visitas"]
    periodos_aplicados: list[str]


class WorkshopSeriesDTO(PageDTO[WorkshopPointDTO]):
    serie: Literal["talleres"] = "talleres"
    periodos_aplicados: list[str]
    ot_clasificadas: int
    ot_sin_ubicacion: int
    ot_no_clasificables: int


SeriesDTO = TrendSeriesDTO | AgeSeriesDTO | MechanicSeriesDTO | BusSeriesDTO | WorkshopSeriesDTO


class ExternalWorkshopDTO(DTO):
    nombre_snapshot: str
    ciudad_snapshot: str
    ot: int
    porcentaje_del_total_externo: float | None
