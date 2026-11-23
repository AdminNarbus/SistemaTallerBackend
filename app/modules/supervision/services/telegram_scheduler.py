"""Despacho por vencimientos y cambios de OT, sin sondeo periódico."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.supervision.models import TelegramEnvio
from app.modules.supervision.services.telegram_service import telegram_service
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.services.telegram_solicitud_service import despachar_solicitudes

logger = logging.getLogger(__name__)


class TelegramScheduler:
    def __init__(self):
        self.wake = asyncio.Event()

    async def changed(self, event):
        if event.resource_type == "work_order":
            self.wake.set()

    async def next_deadline(self, db, since=None):
        now = datetime.now(timezone.utc)
        since = since or now
        rows = (await db.execute(select(
            TallerSolicitud.estado, TallerSolicitud.fecha_creacion,
            TallerSolicitud.fecha_liberacion, TallerSolicitud.fecha_primer_ingreso_taller,
        ).where(TallerSolicitud.estado != "FINALIZADO"))).all()
        deadlines = []
        for estado, creada, liberada, ingreso in rows:
            if estado == "LIBERADO":
                fecha, prefijo = liberada or creada, "LIBERADO"
            elif ingreso is None:
                fecha, prefijo = creada, "TALLER"
            else:
                continue
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            for nivel in ("BAJA", "MEDIA", "ALTA", "CRITICA"):
                horas = getattr(settings, f"SUPERVISION_UMBRAL_{prefijo}_HORAS_{nivel}")
                # La consulta de alertas redondea a una décima de hora.
                fecha_limite = fecha + timedelta(hours=horas, minutes=-3, seconds=1)
                if fecha_limite > since:
                    deadlines.append(fecha_limite)
        retry = await db.scalar(select(TelegramEnvio.proximo_intento).where(
            TelegramEnvio.estado == "REINTENTABLE", TelegramEnvio.intentos < 3,
            TelegramEnvio.proximo_intento > since,
        ).order_by(TelegramEnvio.proximo_intento).limit(1))
        if retry:
            deadlines.append(retry.replace(tzinfo=timezone.utc) if retry.tzinfo is None else retry)
        return min(deadlines) if deadlines else None

    async def run(self):
        while True:
            self.wake.clear()
            scan_started = datetime.now(timezone.utc)
            try:
                if settings.TELEGRAM_ENABLED:
                    async with AsyncSessionLocal() as db:
                        await telegram_service.notificar(db)
                if settings.TELEGRAM_SOLICITUDES_ENABLED:
                    await despachar_solicitudes(notificar_programador=False)
                async with AsyncSessionLocal() as db:
                    deadline = await self.next_deadline(db, since=scan_started)
                if deadline is None:
                    await self.wake.wait()
                else:
                    delay = max(0, (deadline - datetime.now(timezone.utc)).total_seconds())
                    try:
                        await asyncio.wait_for(self.wake.wait(), timeout=delay)
                    except asyncio.TimeoutError:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[TELEGRAM] Error al programar vencimientos")
                await self.wake.wait()


telegram_scheduler = TelegramScheduler()
