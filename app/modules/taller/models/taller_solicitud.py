from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.core.sql_functions import Trimmed

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.buses.models.bus import Bus
    from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
    from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico
    from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
    from app.modules.taller.models.taller_solicitud_estado_evento import TallerSolicitudEstadoEvento
    from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
    from app.modules.taller.models.pauta_taller import TallerSolicitudPauta
    from app.modules.taller.models.taller_solicitud_evidencia import TallerSolicitudEvidencia
    from app.modules.taller.models.taller_solicitud_estadia import TallerSolicitudEstadia


class TallerSolicitud(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitudes en PostgreSQL.
    Representa una orden de mantención o solicitud de reparación enviada al taller.
    """

    __tablename__ = "taller_solicitudes"
    __table_args__ = (
        Index('ix_solicitudes_estado_fecha', 'estado', 'fecha_creacion'),
        Index('ix_solicitudes_fecha_creacion', 'fecha_creacion'),
        CheckConstraint("estado IN ('REPORTADO','PENDIENTE','EN_REPARACION','LIBERADO','FINALIZADO')", name="ck_solicitudes_estado"),
        CheckConstraint("length(trim(n_bus)) > 0", name="ck_solicitudes_numero"),
        CheckConstraint("horas_taller_acumuladas IS NULL OR horas_taller_acumuladas >= 0", name="ck_solicitudes_horas"),
        CheckConstraint("horas_demora_primer_ingreso IS NULL OR horas_demora_primer_ingreso >= 0", name="ck_solicitudes_demora"),
        CheckConstraint("fecha_cierre IS NULL OR fecha_cierre >= fecha_creacion", name="ck_solicitudes_cierre"),
        Index(
            "uq_taller_solicitudes_bus_activa",
            "bus_id",
            unique=True,
            postgresql_where=text("bus_id IS NOT NULL AND estado <> 'FINALIZADO'"),
            sqlite_where=text("bus_id IS NOT NULL AND estado <> 'FINALIZADO'"),
        ),
        Index(
            "uq_taller_solicitudes_n_bus_activa_sin_bus_id",
            func.lower(Trimmed(text("n_bus"))),
            unique=True,
            postgresql_where=text("bus_id IS NULL AND estado <> 'FINALIZADO'"),
            sqlite_where=text("bus_id IS NULL AND estado <> 'FINALIZADO'"),
        ),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    n_bus: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    bus_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("buses.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    
    usuario_creador_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    mecanico_cierre_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    estado: Mapped[str] = mapped_column(
        String(50), default="PENDIENTE", server_default="PENDIENTE", nullable=False, index=True
    )  # PENDIENTE, EN_REPARACION, LIBERADO, FINALIZADO

    descripcion_general: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    foto_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
    fecha_cierre: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fecha_liberacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    fecha_primer_ingreso_taller: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    horas_demora_primer_ingreso: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 1), nullable=True
    )
    horas_taller_acumuladas: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 1), default=0.0, nullable=True
    )

    motivo_incompleto_checklist: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    motivo_cierre_parcial: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    # Relaciones
    bus: Mapped[Optional["Bus"]] = relationship(
        "Bus", foreign_keys=[bus_id], lazy="selectin"
    )
    creador: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", foreign_keys=[usuario_creador_id], lazy="selectin"
    )
    mecanico_cierre: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", foreign_keys=[mecanico_cierre_id], lazy="selectin"
    )

    detalles: Mapped[List["TallerSolicitudDetalle"]] = relationship(
        "TallerSolicitudDetalle", back_populates="solicitud", passive_deletes="all", lazy="selectin"
    )
    mecanicos: Mapped[List["TallerSolicitudMecanico"]] = relationship(
        "TallerSolicitudMecanico", back_populates="solicitud", passive_deletes="all", lazy="selectin"
    )
    estado_eventos: Mapped[List["TallerSolicitudEstadoEvento"]] = relationship(
        "TallerSolicitudEstadoEvento", back_populates="solicitud",
        passive_deletes="all", lazy="raise",
        foreign_keys="TallerSolicitudEstadoEvento.solicitud_id",
    )
    comentarios: Mapped[List["TallerSolicitudComentario"]] = relationship(
        "TallerSolicitudComentario", back_populates="solicitud", passive_deletes="all", lazy="selectin"
    )
    asignaciones_fallas: Mapped[List["TallerAsignacionFalla"]] = relationship(
        "TallerAsignacionFalla", back_populates="solicitud", passive_deletes="all", lazy="selectin", foreign_keys="TallerAsignacionFalla.solicitud_id"
    )
    pauta_respuestas: Mapped[List["TallerSolicitudPauta"]] = relationship(
        "TallerSolicitudPauta", back_populates="solicitud", passive_deletes="all", lazy="selectin"
    )
    evidencias: Mapped[List["TallerSolicitudEvidencia"]] = relationship(
        "TallerSolicitudEvidencia", back_populates="solicitud", passive_deletes="all", lazy="selectin", foreign_keys="TallerSolicitudEvidencia.solicitud_id"
    )
    estadias: Mapped[List["TallerSolicitudEstadia"]] = relationship(
        "TallerSolicitudEstadia", back_populates="solicitud", passive_deletes="all", lazy="selectin"
    )


