from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, text, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.taller.models.taller_solicitud import TallerSolicitud
    from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle


class TallerAsignacionFalla(Base):
    """
    Modelo ORM mapeado a la tabla taller_asignacion_fallas en PostgreSQL.
    Representa la asignación atómica de una falla específica a un mecánico específico
    dentro de una solicitud de taller.
    Soporta co-responsabilidad (2 o más mecánicos trabajando en la misma falla).
    """

    __tablename__ = "taller_asignacion_fallas"
    __table_args__ = (
        Index('ix_asig_fallas_mec_activo', 'mecanico_id', 'is_activo'),
        ForeignKeyConstraint(["detalle_id", "solicitud_id"],
                             ["taller_solicitud_detalles.id", "taller_solicitud_detalles.solicitud_id"],
                             name="fk_asignaciones_detalle_ot", ondelete="RESTRICT"),
        Index("uq_asignacion_falla_activa", "detalle_id", "mecanico_id", unique=True,
              postgresql_where=text("is_activo = true"), sqlite_where=text("is_activo = 1")),
        CheckConstraint("origen IN ('SUPERVISOR','AUTOASIGNACION','MECANICO')", name="ck_asignaciones_origen"),
        CheckConstraint("duracion_minutos IS NULL OR duracion_minutos >= 0", name="ck_asignaciones_duracion"),
        CheckConstraint("fecha_desasignacion IS NULL OR fecha_desasignacion >= fecha_asignacion", name="ck_asignaciones_fechas"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    detalle_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    mecanico_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    asignado_por_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    origen: Mapped[str] = mapped_column(
        String(50), default="SUPERVISOR", server_default="SUPERVISOR", nullable=False
    )  # 'SUPERVISOR', 'AUTOASIGNACION'
    is_activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False, index=True)

    fecha_asignacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_desasignacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resuelto_en_esta_asignacion: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    duracion_minutos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comentario: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship(
        "TallerSolicitud", back_populates="asignaciones_fallas", foreign_keys=[solicitud_id]
    )
    detalle: Mapped["TallerSolicitudDetalle"] = relationship(
        "TallerSolicitudDetalle", back_populates="asignaciones", foreign_keys=[detalle_id]
    )
    mecanico: Mapped["Usuario"] = relationship(
        "Usuario", foreign_keys=[mecanico_id], lazy="selectin"
    )
    asignado_por: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", foreign_keys=[asignado_por_id], lazy="selectin"
    )
