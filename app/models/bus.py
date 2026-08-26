from typing import TYPE_CHECKING, Optional, List
from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.reporte_neumatico import ReporteNeumatico


class Bus(Base):
    """Modelo mapeado a la tabla buses existente en la BD."""

    __tablename__ = "buses"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    n_bus: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patente: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tipo_bus: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reportes_neumaticos: Mapped[List["ReporteNeumatico"]] = relationship(
        "ReporteNeumatico", back_populates="bus"
    )
