import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ResourceType = Literal["work_order", "bus", "user"]


class RealtimeEvent(BaseModel):
    """Mensaje liviano de invalidación; REST sigue siendo la fuente de verdad."""

    type: Literal["resource.changed"] = "resource.changed"
    schema_version: int = 1
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resource_type: ResourceType
    resource_id: int
    action: str
    actor_id: Optional[int] = None
    related_type: Optional[str] = None
    related_id: Optional[int] = None
    version: Optional[datetime] = None


async def publish_event(event: RealtimeEvent) -> None:
    """Publica sin afectar una mutación ya confirmada si el canal falla."""
    from app.core.realtime.runtime import realtime_runtime

    try:
        await realtime_runtime.bus.publish(event)
    except Exception:
        logger.exception("[REALTIME] No se pudo publicar evento | event_id=%s", event.event_id)


def publish_event_soon(event: RealtimeEvent) -> None:
    """Agenda la notificación luego de que el servicio haya confirmado la transacción."""
    asyncio.create_task(publish_event(event), name=f"realtime-{event.event_id}")
