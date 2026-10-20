"""Catálogo de talleres y ubicación inmutable de resultados de fallas."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, TimestampMixin


class Ciudad(Base, TimestampMixin):
    __tablename__ = "ciudades"
    __table_args__ = (
        CheckConstraint("length(trim(nombre)) > 0", name="ck_ciudades_nombre"),
        Index("uq_ciudades_codigo_normalizado", func.lower(func.trim(text("codigo"))), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)


class Taller(Base, TimestampMixin):
    __tablename__ = "talleres"
    __table_args__ = (
        CheckConstraint("tipo IN ('INTERNO','EXTERNO')", name="ck_talleres_tipo"),
        CheckConstraint("length(trim(nombre)) > 0", name="ck_talleres_nombre"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    ciudad_id: Mapped[int] = mapped_column(ForeignKey("ciudades.id", ondelete="RESTRICT"), index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    is_activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    ciudad: Mapped[Ciudad] = relationship(lazy="joined")


class OperacionResultado(Base):
    __tablename__ = "taller_resultado_operaciones"

    operacion_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    accion: Mapped[str] = mapped_column(String(20), nullable=False)
    detalle_id: Mapped[int] = mapped_column(ForeignKey("taller_solicitud_detalles.id", ondelete="RESTRICT"), nullable=False)
    huella: Mapped[str] = mapped_column(String(64), nullable=False)
    respuesta: Mapped[dict] = mapped_column(JSON, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TallerResultadoUbicacion(Base):
    __tablename__ = "taller_resultado_ubicaciones"
    __table_args__ = (
        UniqueConstraint("evento_id", "version", name="uq_resultado_ubicacion_version"),
        UniqueConstraint("operacion_id", name="uq_resultado_ubicacion_operacion"),
        CheckConstraint("version > 0", name="ck_resultado_ubicacion_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evento_id: Mapped[int] = mapped_column(ForeignKey("taller_falla_eventos.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    taller_id: Mapped[int] = mapped_column(ForeignKey("talleres.id", ondelete="RESTRICT"), nullable=False)
    taller_nombre_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    taller_tipo_snapshot: Mapped[str] = mapped_column(String(10), nullable=False)
    ciudad_id_snapshot: Mapped[int] = mapped_column(ForeignKey("ciudades.id", ondelete="RESTRICT"), nullable=False)
    ciudad_nombre_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    actor_nombre_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    operacion_id: Mapped[str] = mapped_column(String(36), nullable=False)
    motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    registrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    colaboradores: Mapped[list["TallerResultadoColaborador"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class TallerResultadoColaborador(Base):
    __tablename__ = "taller_resultado_colaboradores"
    __table_args__ = (UniqueConstraint("ubicacion_id", "taller_id", name="uq_resultado_colaborador"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ubicacion_id: Mapped[int] = mapped_column(ForeignKey("taller_resultado_ubicaciones.id", ondelete="RESTRICT"), nullable=False, index=True)
    taller_id: Mapped[int] = mapped_column(ForeignKey("talleres.id", ondelete="RESTRICT"), nullable=False)
    taller_nombre_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    taller_tipo_snapshot: Mapped[str] = mapped_column(String(10), nullable=False)
    ciudad_id_snapshot: Mapped[int] = mapped_column(ForeignKey("ciudades.id", ondelete="RESTRICT"), nullable=False)
    ciudad_nombre_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)


