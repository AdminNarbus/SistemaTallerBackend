from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.modules.mantencion.models.falla_taller import FallaTaller

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.mantencion.models.taller_solicitud import TallerSolicitud


class TallerSolicitudDetalle(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitud_detalles en PostgreSQL.
    Representa cada punto de falla/avería registrado en una solicitud de mantención.
    """

    __tablename__ = "taller_solicitud_detalles"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    falla_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("fallas_taller.id", ondelete="SET NULL"), nullable=True, index=True
    )
    descripcion_personalizada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    resuelto: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mecanico_resolvio_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )

    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fecha_resolucion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship("TallerSolicitud", back_populates="detalles")
    falla: Mapped[Optional["FallaTaller"]] = relationship("FallaTaller", lazy="selectin")
    mecanico_resolvio: Mapped[Optional["Usuario"]] = relationship("Usuario", lazy="selectin")
