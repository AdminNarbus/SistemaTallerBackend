from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
    from app.modules.taller.models.taller_falla_evento_mecanico import TallerFallaEventoMecanico


class TallerFallaEvento(Base):
    """Evento inmutable que registra la trazabilidad operacional de una falla."""

    __tablename__ = "taller_falla_eventos"
    __table_args__ = (
        CheckConstraint("tipo_evento IN ('REPORTADA','RESUELTA','REABIERTA','INCOMPLETA','FALTA_REPUESTO_ACTIVADA','FALTA_REPUESTO_RETIRADA')", name="ck_eventos_tipo"),
        CheckConstraint("estado_anterior IS NULL OR estado_anterior IN ('PENDIENTE','INCOMPLETA','RESUELTA')", name="ck_eventos_estado_anterior"),
        CheckConstraint("estado_nuevo IS NULL OR estado_nuevo IN ('PENDIENTE','INCOMPLETA','RESUELTA')", name="ck_eventos_estado_nuevo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    detalle_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("taller_solicitud_detalles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tipo_evento: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    usuario_actor_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    actor_nombre_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    estado_anterior: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    estado_nuevo: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    comentario: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fecha_evento: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    detalle: Mapped["TallerSolicitudDetalle"] = relationship(
        "TallerSolicitudDetalle", back_populates="eventos"
    )
    usuario_actor: Mapped[Optional["Usuario"]] = relationship("Usuario", lazy="selectin")
    mecanicos_resolutores: Mapped[List["TallerFallaEventoMecanico"]] = relationship(
        "TallerFallaEventoMecanico",
        back_populates="evento",
        passive_deletes="all",
        lazy="selectin",
    )
