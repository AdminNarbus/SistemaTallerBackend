"""Originales inmutables de consolidaciones administrativas."""
from datetime import datetime
from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base import Base


class TallerConsolidacionArchivo(Base):
    __tablename__ = 'taller_consolidacion_archivos'
    __table_args__ = (UniqueConstraint('tabla', 'registro_id', name='uq_consolidacion_original'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tabla: Mapped[str] = mapped_column(String(80), nullable=False)
    registro_id: Mapped[int] = mapped_column(Integer, nullable=False)
    solicitud_original_id: Mapped[int] = mapped_column(Integer, nullable=False)
    solicitud_destino_id: Mapped[int] = mapped_column(Integer, nullable=False)
    datos_originales: Mapped[dict] = mapped_column(JSON, nullable=False)
    fecha_archivo: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
