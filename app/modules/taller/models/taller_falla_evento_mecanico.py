from typing import TYPE_CHECKING, Optional

from sqlalchemy import UniqueConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.taller.models.taller_falla_evento import TallerFallaEvento


class TallerFallaEventoMecanico(Base):
    """Mecánico participante en un evento de resolución de falla."""

    __tablename__ = "taller_falla_evento_mecanicos"
    __table_args__ = (UniqueConstraint("evento_id", "mecanico_id", name="uq_evento_mecanico"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    evento_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("taller_falla_eventos.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    mecanico_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("usuarios.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    mecanico_nombre_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)

    evento: Mapped["TallerFallaEvento"] = relationship(
        "TallerFallaEvento", back_populates="mecanicos_resolutores"
    )
    mecanico: Mapped[Optional["Usuario"]] = relationship("Usuario", lazy="selectin")
