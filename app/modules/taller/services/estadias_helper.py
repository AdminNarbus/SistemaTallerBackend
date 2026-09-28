import logging
from datetime import datetime
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_estadia import TallerSolicitudEstadia
from app.modules.taller.repository.taller_repository import (
    TallerRepository,
    taller_repository,
)
from app.modules.taller.utils import calcular_horas_en_taller

logger = logging.getLogger(__name__)


def attach_comentario_safe(
    solicitud: Any, comentario: Any, usuario_nombre: Optional[str] = None
) -> None:
    """Adjunta un comentario de manera segura en memoria evitando disparar lazy loading."""
    if usuario_nombre:
        comentario._usuario_nombre_cached = usuario_nombre
    if "comentarios" in getattr(solicitud, "__dict__", {}) and solicitud.__dict__["comentarios"] is not None:
        solicitud.__dict__["comentarios"].append(comentario)
    else:
        if not hasattr(solicitud, "_comentarios_nuevos") or solicitud._comentarios_nuevos is None:
            solicitud._comentarios_nuevos = []
        solicitud._comentarios_nuevos.append(comentario)


def attach_mecanico_safe(solicitud: Any, mecanico: Any) -> None:
    """Adjunta un mecánico de manera segura en memoria evitando disparar lazy loading."""
    if "mecanicos" in getattr(solicitud, "__dict__", {}) and solicitud.__dict__["mecanicos"] is not None:
        solicitud.__dict__["mecanicos"].append(mecanico)
    else:
        if not hasattr(solicitud, "_mecanicos_nuevos") or solicitud._mecanicos_nuevos is None:
            solicitud._mecanicos_nuevos = []
        solicitud._mecanicos_nuevos.append(mecanico)


async def asegurar_ingreso_taller_y_estadia(
    repo: TallerRepository,
    db: AsyncSession,
    solicitud: TallerSolicitud,
    now: datetime,
) -> None:
    """
    Garantiza que el bus quede marcado físicamente en taller (bus.en_taller = True),
    registra la demora de primer ingreso si es la primera vez que entra a taller,
    y abre una nueva estadía (#N+1) si no existe una estadía abierta activa.
    """
    # 1. Asegurar bus en taller
    if solicitud.bus:
        solicitud.bus.en_taller = True
    elif solicitud.bus_id:
        bus = await repo.get_bus_by_id(db, solicitud.bus_id)
        if bus:
            bus.en_taller = True
            solicitud.bus = bus

    # 2. Registrar fecha de primer ingreso a taller y horas de demora
    if not solicitud.fecha_primer_ingreso_taller:
        solicitud.fecha_primer_ingreso_taller = now
        if solicitud.fecha_creacion:
            solicitud.horas_demora_primer_ingreso = (
                calcular_horas_en_taller(solicitud.fecha_creacion, now) or 0.0
            )
        else:
            solicitud.horas_demora_primer_ingreso = 0.0

    # 3. Limpiar fecha_liberacion activa si existía
    solicitud.fecha_liberacion = None

    # 4. Verificar si ya tiene una estadía abierta en memoria o BD
    estadia_abierta = None
    visita_siguiente = 1

    from sqlalchemy import inspect
    from sqlalchemy.orm.attributes import NO_VALUE

    insp = inspect(solicitud)
    estadias_cargadas = bool(
        insp
        and "estadias" in insp.attrs
        and insp.attrs.estadias.loaded_value is not NO_VALUE
    )

    if estadias_cargadas and solicitud.estadias is not None:
        estadia_abierta = next(
            (e for e in solicitud.estadias if e.fecha_salida is None), None
        )
        visitas_existentes = [
            e.numero_visita
            for e in solicitud.estadias
            if getattr(e, "numero_visita", None)
        ]
        visita_siguiente = (
            (max(visitas_existentes) + 1)
            if visitas_existentes
            else (len(solicitud.estadias) + 1)
        )
    else:
        estadia_abierta, conteo_prev = await repo.get_info_estadia_para_ingreso(
            db, solicitud.id
        )
        visita_siguiente = conteo_prev + 1

    if not estadia_abierta:
        nueva_estadia = TallerSolicitudEstadia(
            solicitud_id=solicitud.id,
            numero_visita=visita_siguiente,
            fecha_ingreso=now,
        )
        repo.add_estadia(db, nueva_estadia)
        if estadias_cargadas:
            if solicitud.estadias is None:
                solicitud.estadias = []
            solicitud.estadias.append(nueva_estadia)
        logger.info(
            "[MANTENCION-TELEMETRIA] Nueva estadía abierta | solicitud_id=%s | visita=#%s | fecha_ingreso=%s",
            solicitud.id,
            nueva_estadia.numero_visita,
            now,
        )


async def cerrar_estadia_activa(
    repo: TallerRepository,
    db: AsyncSession,
    solicitud: TallerSolicitud,
    now: datetime,
    motivo_salida: str,
) -> None:
    """
    Cierra la estadía activa abierta (fecha_salida = now), computa la duración exacta
    en horas de esa visita, incrementa horas_taller_acumuladas en la OT y marca bus.en_taller = False.
    """
    estadia_abierta = None
    from sqlalchemy import inspect
    from sqlalchemy.orm.attributes import NO_VALUE

    insp = inspect(solicitud)
    estadias_cargadas = bool(
        insp
        and "estadias" in insp.attrs
        and insp.attrs.estadias.loaded_value is not NO_VALUE
    )

    if estadias_cargadas and solicitud.estadias is not None:
        estadia_abierta = next(
            (e for e in solicitud.estadias if e.fecha_salida is None), None
        )

    if not estadia_abierta:
        estadia_abierta = await repo.get_ultima_estadia_abierta(
            db, solicitud.id
        )

    if estadia_abierta:
        estadia_abierta.fecha_salida = now
        duracion_horas = (
            calcular_horas_en_taller(estadia_abierta.fecha_ingreso, now) or 0.0
        )
        estadia_abierta.horas_estadia = duracion_horas
        estadia_abierta.motivo_salida = motivo_salida
        db.add(estadia_abierta)

        horas_previas = float(solicitud.horas_taller_acumuladas or 0.0)
        solicitud.horas_taller_acumuladas = round(horas_previas + duracion_horas, 1)
        logger.info(
            "[MANTENCION-TELEMETRIA] Estadía cerrada | solicitud_id=%s | visita=#%s | horas=%s | motivo='%s' | acumuladas=%s",
            solicitud.id,
            estadia_abierta.numero_visita,
            duracion_horas,
            motivo_salida,
            solicitud.horas_taller_acumuladas,
        )

    # Marcar bus fuera de taller físico
    if solicitud.bus:
        solicitud.bus.en_taller = False
    elif solicitud.bus_id:
        bus = await repo.get_bus_by_id(db, solicitud.bus_id)
        if bus:
            bus.en_taller = False
            solicitud.bus = bus
