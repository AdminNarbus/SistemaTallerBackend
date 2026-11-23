"""Persistencia del control preventivo; no conserva archivos Excel ni borradores."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin


class ControlMantencion(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "control_mantenciones"
    __table_args__ = (
        CheckConstraint(
            "kilometraje IS NULL OR kilometraje >= 0", name="ck_control_mantenciones_km"
        ),
        CheckConstraint(
            "estado IN ('completa','incompleta')", name="ck_control_mantenciones_estado"
        ),
        Index("ix_control_mantenciones_bus_fecha", "bus_id", "fecha"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bus_id: Mapped[int] = mapped_column(
        ForeignKey("buses.id", ondelete="RESTRICT"), nullable=False
    )
    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    kilometraje: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tipo_mantencion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    certificado: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="incompleta"
    )
    activa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    usuario_creacion_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    usuario_actualizacion_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ControlKilometraje(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "control_kilometrajes"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('aceptado','pendiente','excluido','error','ignorado')",
            name="ck_control_kilometrajes_estado",
        ),
        CheckConstraint(
            "origen IN ('excel','manual')", name="ck_control_kilometrajes_origen"
        ),
        CheckConstraint(
            "estado <> 'aceptado' OR (bus_id IS NOT NULL AND fecha IS NOT NULL AND kilometraje IS NOT NULL AND kilometraje >= 0)",
            name="ck_control_kilometrajes_aceptado",
        ),
        Index("ix_control_kilometrajes_bus_fecha", "bus_id", "fecha"),
        Index("ix_control_kilometrajes_carga", "evento_carga_id"),
        Index("ix_control_kilometrajes_estado", "estado"),
        Index(
            "uq_control_kilometrajes_aceptados",
            "bus_id",
            "fecha",
            "kilometraje",
            unique=True,
            postgresql_where=text("estado = 'aceptado'"),
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bus_id: Mapped[int | None] = mapped_column(
        ForeignKey("buses.id", ondelete="RESTRICT"), nullable=True
    )
    numero_bus_origen: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    kilometraje: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    estado: Mapped[str] = mapped_column(String(30), nullable=False)
    origen: Mapped[str] = mapped_column(String(20), nullable=False)
    evento_carga_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_mantenciones_eventos.id", ondelete="RESTRICT"),
        nullable=True,
    )
    fila_origen: Mapped[int | None] = mapped_column(Integer, nullable=True)
    datos_origen: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        server_default=text("'{}'"),
    )
    observaciones: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        server_default=text("'[]'"),
    )
    usuario_creacion_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    usuario_actualizacion_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ControlEvento(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "control_mantenciones_eventos"
    __table_args__ = (
        Index("ix_control_eventos_bus_fecha", "bus_id", "created_at"),
        Index("ix_control_eventos_tipo_fecha", "tipo", "created_at"),
        Index("ix_control_eventos_mantencion", "mantencion_id"),
        Index("ix_control_eventos_kilometraje", "kilometraje_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    bus_id: Mapped[int | None] = mapped_column(
        ForeignKey("buses.id", ondelete="RESTRICT"), nullable=True
    )
    mantencion_id: Mapped[int | None] = mapped_column(
        ForeignKey("control_mantenciones.id", ondelete="SET NULL"), nullable=True
    )
    kilometraje_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "control_kilometrajes.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_control_eventos_kilometraje",
        ),
        nullable=True,
    )
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False
    )
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)
    valores_anteriores: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    valores_nuevos: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    metadatos: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        server_default=text("'{}'"),
    )
    clave_operacion: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, unique=True
    )
