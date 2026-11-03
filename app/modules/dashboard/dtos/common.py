from datetime import date, datetime, timezone
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.modules.dashboard.constants import CONTRACT_VERSION, TIMEZONE


def utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


UtcDatetime = Annotated[datetime, AfterValidator(utc)]
T = TypeVar("T")


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetadataDTO(DTO):
    version_contrato: int = CONTRACT_VERSION
    generado_en: UtcDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    zona_horaria: str = TIMEZONE
    fecha_referencia_datos: date | None = None


class EnvelopeDTO(DTO, Generic[T]):
    metadata: MetadataDTO
    data: T


class PageDTO(DTO, Generic[T]):
    items: list[T]
    total: int
    skip: int
    limit: int
