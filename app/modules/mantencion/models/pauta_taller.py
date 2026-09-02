from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.mantencion.models.taller_solicitud import TallerSolicitud


class PautaTallerItem(Base):
    """
    Catálogo maestro de ítems de revisión preventiva en la pauta de taller.
    """

    __tablename__ = "pauta_taller_items"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    categoria: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    item: Mapped[str] = mapped_column(String(255), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TallerSolicitudPauta(Base):
    """
    Registro de respuestas de la pauta de inspección preventiva asociada a una solicitud de mantención.
    """

    __tablename__ = "taller_solicitud_pauta"
    __table_args__ = (
        UniqueConstraint("solicitud_id", "item_id", name="uq_solicitud_pauta_item"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    solicitud_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taller_solicitudes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pauta_taller_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'OK', 'DEFECTO', 'NO_APLICA'
    observacion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mecanico_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relaciones
    solicitud: Mapped["TallerSolicitud"] = relationship(
        "TallerSolicitud", back_populates="pauta_respuestas"
    )
    item: Mapped["PautaTallerItem"] = relationship("PautaTallerItem", lazy="selectin")
    mecanico: Mapped[Optional["Usuario"]] = relationship("Usuario", lazy="selectin")
