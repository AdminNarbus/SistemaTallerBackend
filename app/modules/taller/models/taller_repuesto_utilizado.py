"""Uso declarado de un artículo en una falla concreta."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin


class TallerRepuestoUtilizado(Base, TimestampMixin):
    __tablename__ = "taller_repuestos_utilizados"
    __table_args__ = (
        CheckConstraint("cantidad_utilizada > 0", name="ck_repuestos_utilizados_cantidad"),
        CheckConstraint("(fecha_anulacion IS NULL AND usuario_anulacion_id IS NULL AND nombre_usuario_al_anular IS NULL AND motivo_anulacion IS NULL) OR (fecha_anulacion IS NOT NULL AND usuario_anulacion_id IS NOT NULL AND nombre_usuario_al_anular IS NOT NULL AND motivo_anulacion IS NOT NULL AND length(trim(motivo_anulacion)) > 0 AND fecha_anulacion >= created_at)", name="ck_repuestos_utilizados_anulacion"),
        Index("uq_repuesto_falla_vigente", "falla_detalle_id", "repuesto_id", unique=True, postgresql_where=text("fecha_anulacion IS NULL"), sqlite_where=text("fecha_anulacion IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    falla_detalle_id: Mapped[int] = mapped_column(ForeignKey("taller_solicitud_detalles.id", ondelete="RESTRICT"), nullable=False, index=True)
    repuesto_id: Mapped[int] = mapped_column(ForeignKey("repuestos.id", ondelete="RESTRICT"), nullable=False, index=True)
    cantidad_utilizada: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    unidad_al_registrar: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    usuario_registro_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    codigo_repuesto_al_registrar: Mapped[str] = mapped_column(String(100), nullable=False)
    nombre_repuesto_al_registrar: Mapped[str] = mapped_column(String(300), nullable=False)
    parte_repuesto_al_registrar: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    nombre_usuario_al_registrar: Mapped[str] = mapped_column(String(200), nullable=False)
    fecha_anulacion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    usuario_anulacion_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True)
    nombre_usuario_al_anular: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    motivo_anulacion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
