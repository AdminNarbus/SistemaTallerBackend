from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.mantencion.models.taller_solicitud import TallerSolicitud


class TallerSolicitudEstadia(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitud_estadias en PostgreSQL.
    Registra cada ingreso y salida física de un bus a maestranza para una misma OT,
    permitiendo telemetría exacta de visitas y tiempos particulares acumulados.
    """

    __tablename__ = "taller_solicitud_estadias"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero_visita: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    fecha_ingreso: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_salida: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    horas_estadia: Mapped[Optional[float]] = mapped_column(Numeric(10, 1), nullable=True)
    motivo_salida: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relación bidireccional
    solicitud: Mapped["TallerSolicitud"] = relationship(
        "TallerSolicitud", back_populates="estadias"
    )
