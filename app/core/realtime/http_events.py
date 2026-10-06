"""Adaptador temporal para servicios heredados que aún son invocados directo por routers.

Los nuevos casos de uso deben publicar mediante RealtimeEventBus. Este adaptador evita
perder eventos de los endpoints existentes mientras se mantiene un único contrato.
"""
import re
from typing import Optional, Tuple

import jwt
from fastapi import Request

from app.core.config import settings
from app.core.realtime.events import RealtimeEvent, publish_event_soon


def _actor_id(request: Request) -> Optional[int]:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    try:
        payload = jwt.decode(authorization[7:], settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


def _work_order_event(path: str, method: str) -> Optional[Tuple[int, str, Optional[int]]]:
    if method.upper() not in {"POST", "PATCH", "PUT", "DELETE"}:
        return None
    patterns = (
        (r"/(?:taller|supervision/solicitudes)/(\d+)/autoasignar$", "assignment.changed"),
        (r"/(?:taller|supervision/solicitudes)/(\d+)/asignar$", "assignment.changed"),
        (r"/(?:taller|supervision/solicitudes)/(\d+)/agregar-colaborador$", "team.changed"),
        (r"/(?:taller|supervision/solicitudes)/(\d+)/desasignarme$", "team.changed"),
        (r"/(?:taller|supervision/solicitudes)/(\d+)/liberar-turno$", "shift.released"),
        (r"/(?:taller|supervision/solicitudes)/(\d+)/terminar-avance$", "progress.finished"),
        (r"/(?:taller|supervision/solicitudes)/(\d+)/detalles/(\d+)/(?:check|resolver)$", "failure.status_changed"),
        (r"/(?:taller|supervision/solicitudes)/(\d+)/detalles/(\d+)/repuesto$", "failure.parts_changed"),
        (r"/(?:taller|supervision/solicitudes)/(\d+)/detalles$", "failure.added"),
        (r"/taller/(\d+)/comentarios$", "comment.added"),
        (r"/taller/(\d+)/finalizar$", "finalized"),
        (r"/taller/(\d+)/liberar$", "released"),
        (r"/(?:taller|supervision/solicitudes)/(\d+)/estado$", "state.changed"),
    )
    for expression, action in patterns:
        match = re.search(expression, path)
        if match:
            groups = match.groups()
            return int(groups[0]), action, int(groups[1]) if len(groups) > 1 else None
    return None


def emit_http_mutation_event(request: Request, status_code: int) -> None:
    if not settings.REALTIME_ENABLED or status_code >= 300:
        return
    event_data = _work_order_event(request.url.path, request.method)
    if not event_data:
        return
    solicitud_id, action, detail_id = event_data
    publish_event_soon(RealtimeEvent(
        resource_type="work_order",
        resource_id=solicitud_id,
        action=action,
        actor_id=_actor_id(request),
        related_type="failure" if detail_id else None,
        related_id=detail_id,
    ))
