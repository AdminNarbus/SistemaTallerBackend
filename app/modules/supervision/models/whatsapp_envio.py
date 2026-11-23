"""Registro durable de intentos; no equivale a confirmación de entrega."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin


class WhatsappEnvio(Base, TimestampMixin):
    __tablename__ = "whatsapp_envios"
    __table_args__ = (
        UniqueConstraint("clave", name="uq_whatsapp_envios_clave"),
        CheckConstraint(
            "estado IN ('PENDIENTE','ENVIANDO','ACEPTADO','FALLIDO','INCIERTO','REINTENTABLE')",
            name="ck_whatsapp_envios_estado",
        ),
        CheckConstraint("intentos BETWEEN 1 AND 3", name="ck_whatsapp_envios_intentos"),
        Index("ix_whatsapp_envios_estado_reintento", "estado", "proximo_intento"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    clave: Mapped[str] = mapped_column(String(64), nullable=False)
    solicitud_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(64), nullable=False)
    severidad: Mapped[str] = mapped_column(String(10), nullable=False)
    destinatario: Mapped[str] = mapped_column(String(15), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(16), nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    meta_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    codigo_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proximo_intento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
