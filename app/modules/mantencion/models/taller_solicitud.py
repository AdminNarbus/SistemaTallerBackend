from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario


class TallerSolicitud(Base):
    """
    Modelo ORM mapeado a la tabla taller_solicitudes en PostgreSQL.
    """

    __tablename__ = "taller_solicitudes"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    id_bus: Mapped[Optional[int]] = mapped_column(nullable=True)
    n_bus: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    items: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    foto_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estado: Mapped[Optional[str]] = mapped_column(String(50), default="PENDIENTE")
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=True
    )

    usuario: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", backref="taller_solicitudes"
    )
