"""Cola transaccional y despacho de reportes de conductores."""
import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.supervision.dtos.telegram_dto import TelegramNotificacionDTO, TelegramResultadoDTO
from app.modules.supervision.models import TelegramEnvio
from app.modules.supervision.repository.telegram_repository import MAX_INTENTOS, TelegramRepository
from app.modules.supervision.services.telegram_client import TelegramClient

logger = logging.getLogger(__name__)
TIPO_REPORTE = "SOLICITUD_CHOFER"
MAX_TEXTO = 450
MAX_FALLAS = 3400


def _texto(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:MAX_TEXTO] or "Sin detalle"


def _resumen_fallas(fallas: list[str], descripcion: str | None) -> str:
    """Incluye las fallas informadas dentro del límite de mensajes de Telegram."""
    entradas = [re.sub(r"\s+", " ", falla).strip() for falla in fallas if falla and falla.strip()]
    if not entradas:
        return _texto(descripcion)
    lineas = []
    aviso = "\n… Hay más detalles en el sistema de taller."
    for entrada in entradas:
        linea = f"• {entrada}"
        candidato = "\n".join([*lineas, linea])
        if len(candidato) > MAX_FALLAS - len(aviso):
            if not lineas:
                lineas.append(linea[:MAX_FALLAS - len(aviso)])
            return "\n".join(lineas) + aviso
        lineas.append(linea)
    return "\n".join(lineas)


def encolar_reporte(db: AsyncSession, solicitud, datos: tuple) -> None:
    """Agrega las notificaciones a la transacción que guarda el reporte."""
    nombre, dto, detalles = datos
    fallas = [registro[4] for registro in detalles if registro[4]]
    resumen = _resumen_fallas(fallas, dto.descripcion_general)
    parametros = [_texto(nombre)[:100], _texto(solicitud.n_bus), str(solicitud.id), resumen]
    evento = uuid4().hex
    for numero in settings.TELEGRAM_SOLICITUDES_DESTINATARIOS.split(","):
        clave = hashlib.sha256(f"{TIPO_REPORTE}:{evento}:{numero}".encode()).hexdigest()
        db.add(TelegramEnvio(
            clave=clave, solicitud_id=solicitud.id, tipo=TIPO_REPORTE, severidad="INFO",
            destinatario=numero, mensaje=json.dumps(parametros, ensure_ascii=False),
            estado="PENDIENTE", intentos=1,
        ))


class TelegramSolicitudesService:
    def __init__(self, sender=None) -> None:
        self.sender = sender or TelegramClient()
        self.repo = TelegramRepository()

    async def _reservar(self, db: AsyncSession) -> TelegramNotificacionDTO | None:
        ahora = datetime.now(timezone.utc)
        candidato = select(TelegramEnvio.id).where(
            TelegramEnvio.tipo == TIPO_REPORTE,
            or_(TelegramEnvio.estado == "PENDIENTE", (TelegramEnvio.estado == "REINTENTABLE") &
                (TelegramEnvio.proximo_intento <= ahora) & (TelegramEnvio.intentos < MAX_INTENTOS)),
        ).order_by(TelegramEnvio.id).limit(1).scalar_subquery()
        stmt = update(TelegramEnvio).where(TelegramEnvio.id == candidato, TelegramEnvio.estado.in_(["PENDIENTE", "REINTENTABLE"])).values(
            estado="ENVIANDO", updated_at=ahora,
            intentos=TelegramEnvio.intentos + (TelegramEnvio.estado == "REINTENTABLE").cast(TelegramEnvio.intentos.type),
            proximo_intento=None,
        ).returning(TelegramEnvio)
        registro = (await db.scalars(stmt)).first()
        if registro is None:
            await db.commit()
            return None
        envio = TelegramNotificacionDTO(
            clave=registro.clave, solicitud_id=registro.solicitud_id, tipo=registro.tipo,
            severidad=registro.severidad, destinatario=registro.destinatario,
            mensaje=registro.mensaje, parametros=json.loads(registro.mensaje),
        )
        await db.commit()
        return envio

    async def procesar(self, db: AsyncSession) -> bool:
        """Despacha como máximo un destinatario sin retener transacción durante HTTP."""
        await self.repo.expirar_reservas(db)
        await db.commit()
        envio = await self._reservar(db)
        if envio is None:
            return False
        resultado = await self.sender.enviar(envio)
        registro = await db.scalar(select(TelegramEnvio).where(TelegramEnvio.clave == envio.clave))
        if resultado.estado == "REINTENTABLE" and registro.intentos >= MAX_INTENTOS:
            resultado = TelegramResultadoDTO(estado="FALLIDO", codigo_error="LIMITE_REINTENTOS")
        await self.repo.registrar_resultado(db, (registro.id, resultado))
        await db.commit()
        return True


telegram_solicitudes_service = TelegramSolicitudesService()


async def despachar_solicitudes(notificar_programador: bool = True) -> None:
    """Vacía la cola al confirmar una solicitud o al arrancar, sin sondeo periódico."""
    try:
        while True:
            async with AsyncSessionLocal() as db:
                procesado = await telegram_solicitudes_service.procesar(db)
            if not procesado:
                break
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("[TELEGRAM-SOLICITUDES] Error al procesar cola")
    finally:
        if notificar_programador:
            from app.modules.supervision.services.telegram_scheduler import telegram_scheduler
            telegram_scheduler.wake.set()
