from datetime import datetime
from typing import Optional, TYPE_CHECKING
from decimal import Decimal
from sqlalchemy import CheckConstraint, Index, text, Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.core.sql_functions import Trimmed

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario


class Bus(Base):
    """
    Modelo ORM para la tabla buses.
    Almacena el catálogo central de buses/flota para el taller y gestión de solicitudes.
    """

    __tablename__ = "buses"
    __table_args__ = (
        Index("uq_buses_patente_normalizada", func.upper(Trimmed(text("patente"))), unique=True),
        Index("uq_buses_numero_normalizado", func.lower(Trimmed(text("n_bus"))), unique=True),
        CheckConstraint("length(trim(patente)) > 0", name="ck_buses_patente"),
        CheckConstraint("n_bus IS NULL OR length(trim(n_bus)) > 0", name="ck_buses_numero"),
        CheckConstraint("max_litros IS NULL OR max_litros >= 0", name="ck_buses_litros"),
        CheckConstraint("min IS NULL OR min >= 0", name="ck_buses_min"),
        CheckConstraint("max IS NULL OR max >= 0", name="ck_buses_max"),
        CheckConstraint("min IS NULL OR max IS NULL OR min <= max", name="ck_buses_rango"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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
    # Identificador externo; no representa una entidad administrada por este backend.
    empresa_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    n_bus: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    clasificacion: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    min: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    max: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    tipo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    max_litros: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    en_taller: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
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



