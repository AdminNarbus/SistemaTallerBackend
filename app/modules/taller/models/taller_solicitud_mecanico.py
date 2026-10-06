from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, Index, text, Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.taller.models.taller_solicitud import TallerSolicitud


class TallerSolicitudMecanico(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitud_mecanicos en PostgreSQL.
    Registra el equipo colaborativo asignado a la mantención de un bus.
    Mantiene la historia inmutable de turnos pasados (is_activo = False, fecha_desasignacion).
    """

    __tablename__ = "taller_solicitud_mecanicos"
    __table_args__ = (
        Index('ix_sol_mecanicos_mec_activo', 'mecanico_id', 'is_activo'),
        Index("uq_cuadrilla_activa", "solicitud_id", "mecanico_id", unique=True,
              postgresql_where=text("is_activo = true"), sqlite_where=text("is_activo = 1")),
        CheckConstraint("duracion_minutos IS NULL OR duracion_minutos >= 0", name="ck_cuadrilla_duracion"),
        CheckConstraint("fecha_desasignacion IS NULL OR fecha_desasignacion >= fecha_asignacion", name="ck_cuadrilla_fechas"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    mecanico_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    es_lider_responsable: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    is_activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    asignado_por_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    duracion_minutos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    fecha_asignacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_desasignacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship("TallerSolicitud", back_populates="mecanicos")
    mecanico: Mapped["Usuario"] = relationship("Usuario", foreign_keys=[mecanico_id], lazy="selectin")
    asignado_por: Mapped[Optional["Usuario"]] = relationship("Usuario", foreign_keys=[asignado_por_id], lazy="selectin")

