from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.mantencion.models.taller_solicitud import TallerSolicitud


class TallerSolicitudComentario(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitud_comentarios en PostgreSQL.
    Almacena la bitácora cronológica e inmutable de comentarios registrados por mecánicos y supervisores.
    Tipos: ASIGNACION, CIERRE, GENERAL, ENTREGA_TURNO, SALIDA_MECANICO.
    """

    __tablename__ = "taller_solicitud_comentarios"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(
        String(50), default="GENERAL", nullable=False
    )  # ASIGNACION, CIERRE, GENERAL, ENTREGA_TURNO, SALIDA_MECANICO
    comentario: Mapped[str] = mapped_column(Text, nullable=False)

    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship("TallerSolicitud", back_populates="comentarios")
    usuario: Mapped["Usuario"] = relationship("Usuario", lazy="selectin")
