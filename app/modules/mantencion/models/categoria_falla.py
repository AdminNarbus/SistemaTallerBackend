from typing import Optional
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base


class CategoriaFalla(Base):
    """
    Modelo ORM mapeado a la tabla categorias_falla en PostgreSQL.
    Permite definir categorías de fallas dinámicas (ej: FRENOS, ELECTRICO, MOTOR, CARROCERIA, CLIMATIZACION).
    """

    __tablename__ = "categorias_falla"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
