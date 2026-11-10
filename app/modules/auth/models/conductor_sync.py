from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, TimestampMixin


class ConductorSync(Base, TimestampMixin):
    """Un registro confirmado por mes, atómico con la actualización de usuarios."""

    __tablename__ = "conductor_sync"

    periodo: Mapped[str] = mapped_column(String(7), primary_key=True)
    resultado: Mapped[dict] = mapped_column(JSON, nullable=False)
