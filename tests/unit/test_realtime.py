import pytest

from app.core.realtime.bus import InMemoryRealtimeEventBus
from app.core.realtime.events import RealtimeEvent
from app.core.realtime.http_events import _work_order_event


@pytest.mark.asyncio
async def test_in_memory_bus_delivers_event_to_subscriber():
    bus = InMemoryRealtimeEventBus()
    received = []

    async def subscriber(event):
        received.append(event)

    bus.subscribe(subscriber)
    event = RealtimeEvent(
        resource_type="work_order",
        resource_id=25,
        action="failure.status_changed",
    )

    await bus.publish(event)

    assert received == [event]


def test_http_event_mapping_includes_failure_detail():
    result = _work_order_event(
        "/api/v1/taller/12/detalles/44/check", "PATCH"
    )

    assert result == (12, "failure.status_changed", 44)


def test_http_event_mapping_ignores_read_paths():
    assert _work_order_event("/api/v1/taller/12", "GET") is None
