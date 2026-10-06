from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import CheckConstraint, UniqueConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.taller.models.taller_solicitud import TallerSolicitud
    from app.modules.taller.models.taller_solicitud_evidencia import TallerSolicitudEvidencia


class TallerSolicitudComentario(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitud_comentarios en PostgreSQL.
    Almacena la bitácora cronológica e inmutable de comentarios registrados por mecánicos y supervisores.
    Tipos: ASIGNACION, CIERRE, GENERAL, ENTREGA_TURNO, SALIDA_MECANICO.
    """

    __tablename__ = "taller_solicitud_comentarios"
    __table_args__ = (
        UniqueConstraint("id", "solicitud_id", name="uq_comentarios_id_solicitud"),
        CheckConstraint("tipo IN ('GENERAL','AVANCE','CIERRE','SISTEMA','CAMBIO_ESTADO','ASIGNACION','ENTREGA_TURNO','SALIDA_MECANICO','RESOLUCION','CHECKLIST','REAPERTURA','FALTA_REPUESTO','REPUESTO_DISPONIBLE','SUPERVISION')", name="ck_comentarios_tipo"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(
        String(50), default="GENERAL", server_default="GENERAL", nullable=False
    )  # ASIGNACION, CIERRE, GENERAL, ENTREGA_TURNO, SALIDA_MECANICO
    comentario: Mapped[str] = mapped_column(Text, nullable=False)

    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship("TallerSolicitud", back_populates="comentarios")
    usuario: Mapped["Usuario"] = relationship("Usuario", lazy="selectin")
    adjuntos: Mapped[List["TallerSolicitudEvidencia"]] = relationship(
        "TallerSolicitudEvidencia", back_populates="comentario", lazy="selectin", passive_deletes="all", foreign_keys="TallerSolicitudEvidencia.comentario_id"
    )
