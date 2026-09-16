from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.buses.models.bus import Bus
    from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
    from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
    from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
    from app.modules.mantencion.models.taller_asignacion_falla import TallerAsignacionFalla
    from app.modules.mantencion.models.pauta_taller import TallerSolicitudPauta
    from app.modules.mantencion.models.taller_solicitud_evidencia import TallerSolicitudEvidencia


class TallerSolicitud(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitudes en PostgreSQL.
    Representa una orden de mantención o solicitud de reparación enviada al taller.
    """

    __tablename__ = "taller_solicitudes"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    n_bus: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    bus_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("buses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    usuario_creador_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mecanico_cierre_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )

    estado: Mapped[str] = mapped_column(
        String(50), default="REPORTADO", nullable=False, index=True
    )  # REPORTADO, PENDIENTE, EN_REPARACION, LIBERADO, FINALIZADO

    descripcion_general: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    foto_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_cierre: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
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
        "TallerSolicitudDetalle", back_populates="solicitud", cascade="all, delete-orphan", lazy="selectin"
    )
    mecanicos: Mapped[List["TallerSolicitudMecanico"]] = relationship(
        "TallerSolicitudMecanico", back_populates="solicitud", cascade="all, delete-orphan", lazy="selectin"
    )
    comentarios: Mapped[List["TallerSolicitudComentario"]] = relationship(
        "TallerSolicitudComentario", back_populates="solicitud", cascade="all, delete-orphan", lazy="selectin"
    )
    asignaciones_fallas: Mapped[List["TallerAsignacionFalla"]] = relationship(
        "TallerAsignacionFalla", back_populates="solicitud", cascade="all, delete-orphan", lazy="selectin"
    )
    pauta_respuestas: Mapped[List["TallerSolicitudPauta"]] = relationship(
        "TallerSolicitudPauta", back_populates="solicitud", cascade="all, delete-orphan", lazy="selectin"
    )
    evidencias: Mapped[List["TallerSolicitudEvidencia"]] = relationship(
        "TallerSolicitudEvidencia", back_populates="solicitud", cascade="all, delete-orphan", lazy="selectin"
    )


