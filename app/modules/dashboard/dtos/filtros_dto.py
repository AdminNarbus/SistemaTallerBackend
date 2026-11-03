from datetime import date
import re
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.core.exceptions import BusinessRuleException
from app.modules.dashboard.constants import (
    AGE_GROUPS,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SELECTION_FIELDS,
    WORKSHOP_GROUPS,
)
from app.modules.dashboard.dtos.common import DTO
from app.modules.taller.constants import EstadoFalla, EstadoSolicitud

PositiveId = Annotated[int, Field(gt=0)]
Month = Annotated[int, Field(ge=1, le=12)]
Year = Annotated[int, Field(ge=1, le=9999)]
Period = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
SeriesName = Literal[
    "tendencia", "antiguedad", "mecanicos", "buses-fallas", "buses-visitas", "talleres"
]
ResourceName = Literal["buses", "solicitudes", "mecanicos", "periodos"]


def bus_key(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"^0+(?=\d)", "", re.sub(r"^#\s*", "", value.strip())) or None


class GeneralQueryDTO(DTO):
    bus_id: PositiveId | None = None
    n_bus: str | None = Field(None, max_length=50)
    solicitud_id: PositiveId | None = None
    estados: list[EstadoSolicitud | Literal["SOLICITADO"]] = Field(default_factory=list, max_length=6)
    mecanicos_ids: list[PositiveId] = Field(default_factory=list, max_length=MAX_LIMIT)
    meses: list[Month] = Field(default_factory=list, max_length=12)
    anios: list[Year] = Field(default_factory=list, max_length=MAX_LIMIT)

    @field_validator("n_bus", mode="before")
    @classmethod
    def normalize_bus(cls, value):
        return bus_key(value)

    @model_validator(mode="after")
    def exclusive_bus(self):
        if self.bus_id is not None and self.n_bus is not None:
            raise BusinessRuleException("Use bus_id o n_bus, no ambos.")
        return self


class PageQueryDTO(GeneralQueryDTO):
    skip: int = Field(0, ge=0)
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class SeriesQueryDTO(PageQueryDTO):
    periodos: list[Period] = Field(default_factory=list, max_length=MAX_LIMIT)


class SolicitudesQueryDTO(SeriesQueryDTO):
    tabla_n_bus: str | None = Field(None, max_length=50)
    tabla_ot: str | None = Field(None, max_length=30)
    tabla_estados: list[EstadoSolicitud | Literal["SOLICITADO"]] = Field(default_factory=list, max_length=6)
    tabla_periodos: list[Period] = Field(default_factory=list, max_length=MAX_LIMIT)
    tabla_anios: list[Year] = Field(default_factory=list, max_length=MAX_LIMIT)
    seleccion_tipo: (
        Literal[
            "taller",
            "antiguedad",
            "mecanico",
            "bus_fallas",
            "bus_visitas",
            "creadas",
            "terminadas",
            "visitas_bus",
            "reincidencias_bus",
        ]
        | None
    ) = None
    seleccion_grupo: str | None = Field(None, max_length=40)
    seleccion_mecanico_id: PositiveId | None = None
    seleccion_bus_id: PositiveId | None = None
    seleccion_semana: date | None = None
    seleccion_periodo: Period | None = None
    seleccion_periodos: list[Period] = Field(default_factory=list, max_length=MAX_LIMIT)

    @field_validator("tabla_n_bus", mode="before")
    @classmethod
    def normalize_table_bus(cls, value):
        return bus_key(value)

    @field_validator("tabla_ot", mode="before")
    @classmethod
    def normalize_order(cls, value):
        return value.strip().removeprefix("#").strip() or None if value is not None else None

    @model_validator(mode="after")
    def selection_contract(self):
        required = SELECTION_FIELDS.get(self.seleccion_tipo, set())
        supplied = {
            name
            for name in type(self).model_fields
            if name.startswith("seleccion_")
            and name not in {"seleccion_tipo", "seleccion_periodos"}
            and getattr(self, name) is not None
        }
        if supplied != required or (self.seleccion_periodos and self.seleccion_tipo is None):
            raise BusinessRuleException("Los parámetros de selección no corresponden al gráfico.")
        self._validate_group()
        return self

    def _validate_group(self):
        choices = WORKSHOP_GROUPS if self.seleccion_tipo == "taller" else AGE_GROUPS
        if self.seleccion_grupo is not None and self.seleccion_grupo not in choices:
            raise BusinessRuleException("Grupo de selección inválido.")
        if self.seleccion_semana and self.seleccion_semana.weekday() != 0:
            raise BusinessRuleException("seleccion_semana debe ser un lunes.")


class BusQueryDTO(GeneralQueryDTO):
    """El bus se identifica además por la ruta; los filtros se intersectan."""


class FaultQueryDTO(PageQueryDTO):
    estado_falla: EstadoFalla


class FaultOrdersQueryDTO(FaultQueryDTO):
    descripcion: str = Field(min_length=1, max_length=10000)


class TimelineQueryDTO(PageQueryDTO):
    hito_meses: list[Month] = Field(default_factory=list, max_length=12)
    hito_anios: list[Year] = Field(default_factory=list, max_length=MAX_LIMIT)


class TimelineDetailsQueryDTO(TimelineQueryDTO):
    hito_id: str | None = Field(
        None, pattern=r"^(evento:\d+|derivado:\d+:(CREACION|EN_REPARACION|LIBERADO|FINALIZADO))$"
    )


class FilterQueryDTO(PageQueryDTO):
    q: str | None = Field(None, max_length=100)
    contexto: Literal["general", "maquina", "tabla", "ot", "cronologia"] | None = None
