from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario


class ReporteNeumatico(Base, TimestampMixin):
    """
    Modelo de la tabla reportes_neumaticos.
    Guarda la trazabilidad de tiempos y el vínculo con el bus (n_bus) y usuario logueado.
    """

    __tablename__ = "reportes_neumaticos"

    id: Mapped[int] = mapped_column(
        primary_key=True, index=True, autoincrement=True
    )

    # Claves foráneas (Foreign Keys) y campos identificadores
    usuario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    n_bus: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # Datos del formulario de neumáticos
    tipo_bus: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ruedas: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    precio: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    marca_fuego: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    evidencia_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Trazabilidad de tiempo
    fecha_subida: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones SQLAlchemy ORM
    usuario: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", backref="reportes_neumaticos"
    )
