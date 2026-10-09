"""Originales conservados al corregir visitas automáticas confirmadas como falsas."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class TallerCorreccionVisita(Base):
    __tablename__ = "taller_correcciones_visitas"
    __table_args__ = (UniqueConstraint("estadia_id", name="uq_correccion_visita_estadia"),)

    solicitud_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    estadia_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_correccion: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    datos_originales: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
