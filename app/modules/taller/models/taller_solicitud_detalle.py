from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import CheckConstraint, UniqueConstraint, Index, text, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.modules.taller.constants import EstadoFalla
from app.modules.taller.models.falla_taller import FallaTaller

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.taller.models.taller_solicitud import TallerSolicitud
    from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
    from app.modules.taller.models.taller_falla_evento import TallerFallaEvento


class TallerSolicitudDetalle(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitud_detalles en PostgreSQL.
    Representa cada punto de falla/avería registrado en una solicitud de mantención.
    """

    __tablename__ = "taller_solicitud_detalles"
    __table_args__ = (
        Index('ix_sol_detalles_sol_resuelto', 'solicitud_id', 'resuelto'),
        Index('ix_taller_solicitud_detalles_solicitud_fecha_reporte', 'solicitud_id', 'fecha_reporte'),
        UniqueConstraint("id", "solicitud_id", name="uq_detalles_id_solicitud"),
        CheckConstraint("estado IN ('PENDIENTE','INCOMPLETA','RESUELTA')", name="ck_detalles_estado"),
        CheckConstraint("resuelto = (estado = 'RESUELTA')", name="ck_detalles_resuelto_estado"),
        CheckConstraint("fecha_resolucion IS NULL OR fecha_resolucion >= fecha_creacion", name="ck_detalles_fechas"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    falla_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("fallas_taller.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    descripcion_personalizada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    falla_nombre_snapshot: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    categoria_nombre_snapshot: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    estado: Mapped[str] = mapped_column(
        String(30), default=EstadoFalla.PENDIENTE.value, server_default="PENDIENTE", nullable=False, index=True
    )
    motivo_incompleto: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    resuelto: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    mecanico_resolvio_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    reportado_por_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    falta_repuesto: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    comentario_repuesto: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_resolucion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fecha_reporte: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship("TallerSolicitud", back_populates="detalles")
    falla: Mapped[Optional["FallaTaller"]] = relationship("FallaTaller", lazy="selectin")
    mecanico_resolvio: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", foreign_keys=[mecanico_resolvio_id], lazy="selectin"
    )
    reportado_por: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", foreign_keys=[reportado_por_id], lazy="selectin"
    )
    asignaciones: Mapped[List["TallerAsignacionFalla"]] = relationship(
        "TallerAsignacionFalla", back_populates="detalle", passive_deletes="all", lazy="selectin", foreign_keys="TallerAsignacionFalla.detalle_id"
    )
    eventos: Mapped[List["TallerFallaEvento"]] = relationship(
        "TallerFallaEvento", back_populates="detalle", passive_deletes="all", lazy="selectin"
    )

