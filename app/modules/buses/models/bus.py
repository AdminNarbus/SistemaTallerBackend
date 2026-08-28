from typing import Optional
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class Bus(Base):
    """
    Modelo ORM para la tabla buses (referencia legacy).
    NOTA: La tabla buses no se usa activamente en el sistema de taller.
    Los buses se identifican por su n_bus (string) directamente en las
    tablas taller_solicitudes y reportes_neumaticos, sin FK a esta tabla.
    """

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
