from typing import Optional
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Conductor(Base):
    """Modelo mapeado a la tabla conductores existente en la BD."""

    __tablename__ = "conductores"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    rut: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
