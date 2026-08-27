from typing import Optional
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class Rol(Base):
    """
    Modelo de la tabla roles en la base de datos PostgreSQL.
    Define los roles del sistema (ADMIN, SUPERVISOR, MECANICO, CONDUCTOR).
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        primary_key=True, index=True, autoincrement=True
    )
    nombre: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    descripcion: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
