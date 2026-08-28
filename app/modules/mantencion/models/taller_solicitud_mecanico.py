from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.mantencion.models.taller_solicitud import TallerSolicitud


class TallerSolicitudMecanico(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitud_mecanicos en PostgreSQL.
    Registra el equipo colaborativo asignado a la mantención de un bus.
    Mantiene la historia inmutable de turnos pasados (is_activo = False, fecha_desasignacion).
    """

    __tablename__ = "taller_solicitud_mecanicos"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mecanico_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    es_lider_responsable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    fecha_asignacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_desasignacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship("TallerSolicitud", back_populates="mecanicos")
    mecanico: Mapped["Usuario"] = relationship("Usuario", lazy="selectin")
