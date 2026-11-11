"""Catálogo de repuestos y artículos de taller."""
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin


class Repuesto(Base, TimestampMixin):
    __tablename__ = "repuestos"
    __table_args__ = (
        CheckConstraint("precio IS NULL OR precio >= 0", name="ck_repuestos_precio"),
        CheckConstraint("iva IS NULL OR iva >= 0", name="ck_repuestos_iva"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    parte: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    unidad: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    precio: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 4), nullable=True)
    iva: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 4), nullable=True)
    clasificacion: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    clasificacion_1: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    modelo: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True, nullable=False)
