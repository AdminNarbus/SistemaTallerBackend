import asyncio
import json
import re
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.realtime.runtime import realtime_runtime
from app.modules.auth.constants import RolUsuario
from app.modules.auth.services.auth_service import auth_service

router = APIRouter(tags=["Tiempo real"])
ALLOWED_ROLES = {RolUsuario.MECANICO.value, RolUsuario.SUPERVISOR.value, RolUsuario.ADMIN.value}


def _origin_allowed(origin: str) -> bool:
    if not origin:
        return False
    clean_origin = origin.rstrip("/")
    if clean_origin in {str(item).rstrip("/") for item in settings.effective_cors_origins}:
        return True
    return bool(settings.effective_cors_origin_regex and re.match(settings.effective_cors_origin_regex, clean_origin))


async def _authenticate(websocket: WebSocket):
    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=5)
    except (asyncio.TimeoutError, json.JSONDecodeError):
        await websocket.close(code=4408, reason="Authentication timeout")
        return None
    if message.get("type") != "auth" or not message.get("access_token"):
        await websocket.close(code=4401, reason="Authentication required")
        return None
    try:
        payload = jwt.decode(message["access_token"], settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("typ", "access") != "access":
            raise jwt.InvalidTokenError("Invalid token type")
        user_id = int(payload["sub"])
        expires_at = datetime.fromtimestamp(int(payload["exp"]), timezone.utc)
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        await websocket.close(code=4401, reason="Invalid token")
        return None
    async with AsyncSessionLocal() as db:
        user = await auth_service.get_current_user_profile(db, user_id=user_id)
    if not user:
        await websocket.close(code=4401, reason="Inactive user")
        return None
    if (user.rol or "").upper().strip() not in ALLOWED_ROLES:
        await websocket.close(code=4403, reason="Role not allowed")
        return None
    return user, expires_at


@router.websocket("/realtime/ws")
async def realtime_websocket(websocket: WebSocket) -> None:
    if not settings.REALTIME_ENABLED:
        await websocket.close(code=1013, reason="Realtime disabled")
        return
    if not _origin_allowed(websocket.headers.get("origin", "")):
        await websocket.close(code=4403, reason="Origin not allowed")
        return
    await websocket.accept()
    authentication = await _authenticate(websocket)
    if not authentication:
        return
    user, expires_at = authentication
    await realtime_runtime.connect(websocket, user.id)
    await websocket.send_json({
        "type": "connection.ready",
        "protocol_version": 1,
        "heartbeat_seconds": settings.REALTIME_HEARTBEAT_SECONDS,
        "server_time": datetime.now(timezone.utc).isoformat(),
    })
    try:
        while True:
            seconds_remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
            if seconds_remaining <= 0:
                await websocket.close(code=4401, reason="Token expired")
                break
            message = await asyncio.wait_for(websocket.receive_json(), timeout=seconds_remaining)
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except asyncio.TimeoutError:
        await websocket.close(code=4401, reason="Token expired")
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        await realtime_runtime.disconnect(websocket)


@router.get("/health/realtime", summary="Estado del canal de tiempo real")
async def realtime_health():
    if not settings.REALTIME_ENABLED:
        return {"status": "disabled", "enabled": False, "connections": 0}
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "healthy",
            "enabled": True,
            "connections": realtime_runtime.connection_count,
            "last_event_at": realtime_runtime.last_event_at.isoformat() if realtime_runtime.last_event_at else None,
        },
    )
