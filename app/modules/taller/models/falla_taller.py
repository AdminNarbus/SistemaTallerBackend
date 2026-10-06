from typing import Optional
from sqlalchemy import text, Index, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.modules.taller.models.categoria_falla import CategoriaFalla


class FallaTaller(Base):
    """
    Modelo ORM mapeado a la tabla fallas_taller en PostgreSQL.
    Catálogo de averías y fallas de taller preconcebidas (ej: 'Frenos desgastados', 'Luces quemadas').
    """

    __tablename__ = "fallas_taller"
    __table_args__ = (Index("ix_fallas_taller_cat_active", "categoria_id", "is_active"), {"extend_existing": True})

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    categoria_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categorias_falla.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)

    categoria: Mapped["CategoriaFalla"] = relationship("CategoriaFalla", lazy="selectin")
