"""Historia inmutable de los estados de una orden de trabajo."""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.taller.models.taller_solicitud import TallerSolicitud
    from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario


class TallerSolicitudEstadoEvento(Base):
    __tablename__ = "taller_solicitud_estado_eventos"
    __table_args__ = (
        ForeignKeyConstraint(["comentario_id", "solicitud_id"], ["taller_solicitud_comentarios.id", "taller_solicitud_comentarios.solicitud_id"], name="fk_estado_evento_comentario_ot", ondelete="RESTRICT"),
        UniqueConstraint("comentario_id", name="uq_estado_evento_comentario"),
        Index("ix_estado_evento_cronologia", "solicitud_id", "fecha_evento", "id"),
        CheckConstraint("estado_anterior IS NULL OR estado_anterior IN ('REPORTADO','PENDIENTE','EN_REPARACION','LIBERADO','FINALIZADO')", name="ck_estado_evento_anterior"),
        CheckConstraint("estado_nuevo IS NULL OR estado_nuevo IN ('REPORTADO','PENDIENTE','EN_REPARACION','LIBERADO','FINALIZADO')", name="ck_estado_evento_nuevo"),
        CheckConstraint("origen IN ('OPERACION','BITACORA')", name="ck_estado_evento_origen"),
        CheckConstraint("(tipo_evento = 'CREACION' AND estado_anterior IS NULL AND estado_nuevo IS NOT NULL) OR (tipo_evento = 'CAMBIO_ESTADO' AND estado_anterior IS NOT NULL AND estado_nuevo IS NOT NULL AND estado_anterior <> estado_nuevo) OR (tipo_evento = 'CIERRE_HISTORICO' AND origen = 'BITACORA' AND estado_anterior IS NULL AND estado_nuevo IS NULL)", name="ck_estado_evento_transicion"),
        CheckConstraint("length(trim(actor_nombre_snapshot)) > 0", name="ck_estado_evento_actor"),
        CheckConstraint("origen <> 'BITACORA' OR comentario_id IS NOT NULL", name="ck_estado_evento_fuente"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(Integer, ForeignKey("taller_solicitudes.id", ondelete="RESTRICT"), nullable=False)
    tipo_evento: Mapped[str] = mapped_column(String(30), nullable=False)
    estado_anterior: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    estado_nuevo: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    usuario_actor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True)
    actor_nombre_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    fecha_evento: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comentario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    origen: Mapped[str] = mapped_column(String(20), nullable=False)

    solicitud: Mapped["TallerSolicitud"] = relationship("TallerSolicitud", back_populates="estado_eventos", foreign_keys=[solicitud_id])
    comentario: Mapped[Optional["TallerSolicitudComentario"]] = relationship("TallerSolicitudComentario", foreign_keys=[comentario_id])
