"""Representación única de notas grupales sin alterar sus registros históricos."""

from datetime import datetime, timezone

from app.modules.taller.dtos.averias_dto import AsignacionFallaDTO
from app.modules.taller.dtos.bitacora_dto import SolicitudComentarioDTO
from app.modules.taller.dtos.solicitud_dto import SolicitudDTO


def _instante(fecha: datetime) -> datetime:
    return fecha.replace(tzinfo=timezone.utc) if fecha.tzinfo is None else fecha.astimezone(timezone.utc)


def _mensaje_original(
    asignacion: AsignacionFallaDTO, candidatos: list[SolicitudComentarioDTO],
) -> SolicitudComentarioDTO | None:
    nota = (asignacion.comentario or "").strip()
    coincidencias = [c for c in candidatos if not nota or c.comentario.rstrip().endswith(nota)]
    # No atribuir una nota cuando dos mensajes distintos resultan indistinguibles.
    return coincidencias[0] if len(coincidencias) == 1 else None


def normalizar_avances_fallas(solicitud: SolicitudDTO) -> SolicitudDTO:
    """Muta el DTO: traslada notas identificadas a un avance único por ID y falla.

    La identidad se obtiene del mensaje global y del instante exacto de cierre;
    una nota igual de otro turno permanece como un avance diferente.
    """
    por_fecha: dict[datetime, list[SolicitudComentarioDTO]] = {}
    for comentario in solicitud.comentarios:
        if comentario.tipo == "ENTREGA_TURNO":
            por_fecha.setdefault(_instante(comentario.fecha_registro), []).append(comentario)
    for detalle in solicitud.detalles:
        avances = {c.id: c for c in detalle.historial_avances}
        for asignacion in detalle.historial_asignaciones:
            if asignacion.is_activo or asignacion.fecha_desasignacion is None:
                continue
            candidatos = por_fecha.get(_instante(asignacion.fecha_desasignacion), [])
            mensaje = _mensaje_original(asignacion, candidatos)
            if mensaje is not None:
                avances[mensaje.id] = mensaje
                asignacion.comentario_avance_id = mensaje.id
                asignacion.comentario = None
        detalle.historial_avances = sorted(avances.values(), key=lambda c: (_instante(c.fecha_registro), c.id))
    return solicitud
