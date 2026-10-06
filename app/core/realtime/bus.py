from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Dict
from uuid import uuid4

from app.core.realtime.events import RealtimeEvent

RealtimeSubscriber = Callable[[RealtimeEvent], Awaitable[None]]


class RealtimeEventBus(ABC):
    @abstractmethod
    async def publish(self, event: RealtimeEvent) -> None: ...

    @abstractmethod
    def subscribe(self, subscriber: RealtimeSubscriber) -> str: ...

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> None: ...


class InMemoryRealtimeEventBus(RealtimeEventBus):
    """Bus local intercambiable por Redis sin cambiar los casos de uso."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, RealtimeSubscriber] = {}

    async def publish(self, event: RealtimeEvent) -> None:
        for subscriber in tuple(self._subscribers.values()):
            await subscriber(event)

    def subscribe(self, subscriber: RealtimeSubscriber) -> str:
        subscription_id = str(uuid4())
        self._subscribers[subscription_id] = subscriber
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        self._subscribers.pop(subscription_id, None)
