from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.taller.models.taller_solicitud import TallerSolicitud
    from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle


class TallerSolicitudEvidencia(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitud_evidencias en PostgreSQL.
    Representa cada fotografía o evidencia multimedia asociada a una solicitud de taller.
    Sigue estrictamente la Tercera Forma Normal (3NF).
    """

    __tablename__ = "taller_solicitud_evidencias"
    __table_args__ = (
        ForeignKeyConstraint(["detalle_id", "solicitud_id"],
                             ["taller_solicitud_detalles.id", "taller_solicitud_detalles.solicitud_id"],
                             name="fk_evidencias_detalle_ot", ondelete="RESTRICT"),
        ForeignKeyConstraint(["comentario_id", "solicitud_id"],
                             ["taller_solicitud_comentarios.id", "taller_solicitud_comentarios.solicitud_id"],
                             name="fk_evidencias_comentario_ot", ondelete="RESTRICT"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_evidencias_tamano"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    detalle_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True
    )
    usuario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    comentario_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship("TallerSolicitud", back_populates="evidencias", foreign_keys=[solicitud_id])
    detalle: Mapped[Optional["TallerSolicitudDetalle"]] = relationship("TallerSolicitudDetalle", lazy="selectin", foreign_keys=[detalle_id])
    comentario: Mapped[Optional["TallerSolicitudComentario"]] = relationship(
        "TallerSolicitudComentario", back_populates="adjuntos", foreign_keys=[comentario_id]
    )
    usuario: Mapped[Optional["Usuario"]] = relationship("Usuario", lazy="selectin")
