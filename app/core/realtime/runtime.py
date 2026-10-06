import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import DefaultDict, Dict, Optional, Set

from fastapi import WebSocket

from app.core.realtime.bus import InMemoryRealtimeEventBus
from app.core.realtime.events import RealtimeEvent

logger = logging.getLogger(__name__)


class RealtimeRuntime:
    def __init__(self) -> None:
        self.bus = InMemoryRealtimeEventBus()
        self._connections: DefaultDict[int, Set[WebSocket]] = defaultdict(set)
        self._queues: Dict[WebSocket, asyncio.Queue[RealtimeEvent]] = {}
        self._writers: Dict[WebSocket, asyncio.Task] = {}
        self._subscription_id: Optional[str] = None
        self.last_event_at: Optional[datetime] = None

    async def start(self) -> None:
        if self._subscription_id is None:
            self._subscription_id = self.bus.subscribe(self.broadcast)

    async def stop(self) -> None:
        if self._subscription_id:
            self.bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
        for websocket in tuple(self._queues):
            await websocket.close(code=1012, reason="Service restart")
        self._connections.clear()
        self._queues.clear()
        for task in self._writers.values():
            task.cancel()
        self._writers.clear()

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=100)
        self._connections[user_id].add(websocket)
        self._queues[websocket] = queue
        self._writers[websocket] = asyncio.create_task(self._writer(websocket, queue))

    async def disconnect(self, websocket: WebSocket) -> None:
        for user_id, sockets in tuple(self._connections.items()):
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(user_id, None)
        self._queues.pop(websocket, None)
        task = self._writers.pop(websocket, None)
        if task:
            task.cancel()

    async def disconnect_user(self, user_id: int) -> None:
        for websocket in tuple(self._connections.get(user_id, set())):
            await websocket.close(code=4403, reason="User disabled")

    async def broadcast(self, event: RealtimeEvent) -> None:
        self.last_event_at = datetime.now(timezone.utc)
        logger.info(
            "[REALTIME] Evento distribuido | event_id=%s recurso=%s:%s accion=%s conexiones=%s",
            event.event_id,
            event.resource_type,
            event.resource_id,
            event.action,
            self.connection_count,
        )
        for websocket, queue in tuple(self._queues.items()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("[REALTIME] Cliente lento desconectado")
                await websocket.close(code=1013, reason="Client too slow")

    async def _writer(self, websocket: WebSocket, queue: asyncio.Queue[RealtimeEvent]) -> None:
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event.model_dump(mode="json"))
                logger.debug("[REALTIME] Evento enviado a socket | event_id=%s", event.event_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("[REALTIME] Writer WebSocket terminado", exc_info=True)

    @property
    def connection_count(self) -> int:
        return len(self._queues)


realtime_runtime = RealtimeRuntime()
