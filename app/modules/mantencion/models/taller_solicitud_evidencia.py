from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
    from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle


class TallerSolicitudEvidencia(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitud_evidencias en PostgreSQL.
    Representa cada fotografía o evidencia multimedia asociada a una solicitud de taller.
    Sigue estrictamente la Tercera Forma Normal (3NF).
    """

    __tablename__ = "taller_solicitud_evidencias"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    detalle_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("taller_solicitud_detalles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    usuario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship("TallerSolicitud", back_populates="evidencias")
    detalle: Mapped[Optional["TallerSolicitudDetalle"]] = relationship("TallerSolicitudDetalle", lazy="selectin")
    usuario: Mapped[Optional["Usuario"]] = relationship("Usuario", lazy="selectin")
