from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.modules.auth.models.usuario import Usuario
    from app.modules.buses.models.bus import Bus


class ReporteNeumatico(Base, TimestampMixin):
    """
    Modelo de la tabla reportes_neumaticos.
    Guarda la trazabilidad de tiempos y el vínculo con el bus (n_bus, bus_id) y usuario logueado.
    """

    __tablename__ = "reportes_neumaticos"
    __table_args__ = (
        CheckConstraint("json_array_length(ruedas) = 1", name="ck_neumaticos_rueda_unica"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )

    # Claves foráneas (Foreign Keys) y campos identificadores
    usuario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bus_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("buses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    n_bus: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # Datos del formulario de neumáticos
    tipo_bus: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ruedas: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    ruedas_originales: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    reporte_origen_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("reportes_neumaticos.id", name="fk_neumaticos_reporte_origen", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Valor legado conservado para no perder importes históricos; fuera de la API vigente.
    precio_historico: Mapped[Optional[Decimal]] = mapped_column("precio", Numeric(12, 2), nullable=True)
    marca_fuego: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    evidencia_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Trazabilidad de tiempo
    fecha_subida: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relaciones SQLAlchemy ORM
    bus: Mapped[Optional["Bus"]] = relationship("Bus", foreign_keys=[bus_id], lazy="selectin")
    usuario: Mapped[Optional["Usuario"]] = relationship(
        "Usuario", backref="reportes_neumaticos"
    )
