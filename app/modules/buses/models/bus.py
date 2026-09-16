from datetime import datetime
from typing import Optional, TYPE_CHECKING
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario


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
    en_taller: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Campos de trazabilidad y auditoría temporal
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_baja: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    motivo_baja: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usuario_baja_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )

    usuario_baja: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", foreign_keys=[usuario_baja_id], lazy="selectin"
    )



