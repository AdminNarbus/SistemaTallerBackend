"""Utilidades de servicio para preservar la historia inmutable de cada falla."""

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.taller.models.taller_falla_evento import TallerFallaEvento
from app.modules.taller.models.taller_falla_evento_mecanico import TallerFallaEventoMecanico
from app.modules.taller.repository.taller_repository import TallerRepository


def _nombre_usuario(usuario: object | None, fallback: str) -> str:
    return getattr(usuario, "nombre_completo", None) or getattr(usuario, "nombre", None) or fallback


def registrar_evento_falla(
    db: AsyncSession,
    repository: TallerRepository,
    *,
    detalle_id: int,
    tipo_evento: str,
    actor_id: Optional[int],
    actor_nombre: Optional[str],
    estado_anterior: Optional[str],
    estado_nuevo: Optional[str],
    fecha_evento: datetime,
    comentario: Optional[str] = None,
    mecanicos_resolutores: Iterable[object] = (),
) -> TallerFallaEvento:
    """Persiste un evento de falla y los mecánicos que participaron en su resolución."""
    evento = TallerFallaEvento(
        detalle_id=detalle_id,
        tipo_evento=tipo_evento,
        usuario_actor_id=actor_id,
        actor_nombre_snapshot=actor_nombre or "No registrado",
        estado_anterior=estado_anterior,
        estado_nuevo=estado_nuevo,
        comentario=comentario.strip() if comentario else None,
        fecha_evento=fecha_evento,
    )
    repository.add_evento_falla(db, evento)

    vistos: set[int] = set()
    for mecanico in mecanicos_resolutores:
        mecanico_id = getattr(mecanico, "id", None)
        if mecanico_id is not None and mecanico_id in vistos:
            continue
        if mecanico_id is not None:
            vistos.add(mecanico_id)
        repository.add_evento_falla_mecanico(
            db,
            TallerFallaEventoMecanico(
                evento=evento,
                mecanico_id=mecanico_id,
                mecanico_nombre_snapshot=_nombre_usuario(mecanico, "No registrado"),
            ),
        )
    return evento
