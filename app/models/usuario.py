from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.conductor import Conductor


class Usuario(Base, TimestampMixin):
    """
    Modelo de la tabla usuarios para autenticación y login.
    Relacionado opcionalmente con la tabla conductores vía conductor_id.
    """

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    conductor_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("conductores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    rol: Mapped[str] = mapped_column(String(50), default="CONDUCTOR", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    conductor: Mapped[Optional["Conductor"]] = relationship(
        "Conductor", backref="usuario"
    )
