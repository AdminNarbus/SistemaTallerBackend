from typing import Optional
from decimal import Decimal
from sqlalchemy import Boolean, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class Bus(Base):
    """
    Modelo ORM para la tabla buses.
    Almacena el catálogo central de buses/flota para el taller y gestión de solicitudes.
    """

    __tablename__ = "buses"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    patente: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    n_motor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    n_chasis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    n_carroceria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    marca: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    modelo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    astos: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    anio: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    servicio: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tipo_bus: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    empresa_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    n_bus: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True, unique=True)
    clasificacion: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    min: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    max: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    tipo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    max_litros: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, nullable=True
    )

