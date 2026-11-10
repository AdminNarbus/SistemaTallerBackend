"""Contratos públicos; fechas de Excel inválidas permanecen en el borrador."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

EstadoLectura = Literal[
    "aceptado", "pendiente", "excluido", "error", "ignorado", "duplicado"
]


class DTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Pagina(DTO):
    items: list[dict[str, Any]]
    total: int
    skip: int
    limit: int


class Filtros(DTO):
    bus_id: int | None = None
    mantencion_id: int | None = None
    buscar: str = Field(default="", max_length=100)
    desde: date | None = None
    hasta: date | None = None
    estado: str | None = None
    tipo: Literal["todos", "mantencion", "kilometraje"] = "todos"
    area: Literal["panel", "historial", "eventos", "cargas"] = "historial"
    ordenar: Literal["bus", "restantes", "fecha"] = "bus"
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)


class MantencionCrear(DTO):
    bus_id: int
    fecha: date | None = None
    kilometraje: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    tipo_mantencion: str | None = Field(default=None, max_length=100)
    certificado: str | None = Field(default=None, max_length=100)
    ot: str | None = Field(default=None, max_length=100)
    estado: Literal["completa", "incompleta"] | None = None


class MantencionEditar(DTO):
    version: int = Field(ge=0)
    fecha: date | None = None
    kilometraje: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    tipo_mantencion: str | None = Field(default=None, max_length=100)
    certificado: str | None = Field(default=None, max_length=100)
    ot: str | None = Field(default=None, max_length=100)
    estado: Literal["completa", "incompleta"] | None = None
    activa: bool | None = None


class Version(DTO):
    version: int = Field(ge=0)


class IntervaloEditar(Version):
    intervalo_mantencion_km: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )


class LecturaCrear(DTO):
    bus_id: int
    fecha: date
    kilometraje: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class LecturaEditar(Version):
    fecha: date | None = None
    kilometraje: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )


class Decision(Version):
    accion: Literal["aceptar", "excluir"]


class Comentario(DTO):
    comentario: str = Field(min_length=1, max_length=10000)


class FilaBorrador(DTO):
    id: UUID = Field(default_factory=uuid4)
    fila: int = Field(ge=2)
    numero_bus: str | None = Field(default=None, max_length=50)
    fecha: str | None = Field(default=None, max_length=100)
    kilometraje: str | None = Field(default=None, max_length=100)
    decision: Literal["pendiente", "aceptar", "excluir"] = "pendiente"


class Borrador(DTO):
    clave_operacion: UUID = Field(default_factory=uuid4)
    nombre_archivo: str = Field(min_length=1, max_length=255)
    filas: list[FilaBorrador] = Field(min_length=1, max_length=100000)


class ResultadoFila(DTO):
    fila: FilaBorrador
    bus_id: int | None
    estado: EstadoLectura
    motivos: list[str]
    anterior: dict[str, Any] | None = None
    seleccionada: bool = True


class Revision(DTO):
    borrador: Borrador
    resultados: list[ResultadoFila]
    resumen: dict[str, int]


class ResultadoCarga(DTO):
    carga_id: int
    resumen: dict[str, int]
    buses_afectados: list[int]


class Operacion(DTO):
    mensaje: str


class Recurso(DTO):
    datos: dict[str, Any]


class VistaPrevia(DTO):
    revisiones: list[Revision]


class Panel(Pagina):
    contadores: dict[str, int]
