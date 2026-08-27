from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico


class Bus(Base):
    """Modelo ORM para la tabla buses existente en la base de datos."""

    __tablename__ = "buses"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    n_bus: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    patente: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    marca: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    modelo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, nullable=True
    )

    reportes_neumaticos: Mapped[List["ReporteNeumatico"]] = relationship(
        "ReporteNeumatico", back_populates="bus"
    )
