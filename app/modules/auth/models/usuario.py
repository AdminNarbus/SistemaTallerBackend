from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base
from app.modules.auth.models.rol import Rol


class Usuario(Base):
    """
    Modelo de la tabla usuarios en la base de datos PostgreSQL.
    Vinculado mediante clave foránea (rol_id) a la tabla normalizada roles.
    """

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(
        primary_key=True, index=True, autoincrement=True
    )
    nombre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    apellido: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    rol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    rol_rel: Mapped["Rol"] = relationship("Rol", back_populates="usuarios")

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def rol(self) -> str:
        """Devuelve el nombre del rol en formato texto (ej: 'ADMIN')."""
        return self.rol_rel.nombre if self.rol_rel else "CONDUCTOR"

    @property
    def nombre_completo(self) -> str:
        """Devuelve el nombre completo o username del usuario."""
        if self.nombre and self.apellido:
            return f"{self.nombre} {self.apellido}"
        if self.nombre:
            return self.nombre
        return self.username

