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
from app.modules.supervision.dtos.whatsapp_dto import WhatsappNotificacionDTO, WhatsappResultadoDTO
from app.modules.supervision.models import WhatsappEnvio
from app.modules.supervision.repository.whatsapp_repository import MAX_INTENTOS, WhatsappRepository
from app.modules.supervision.services.whatsapp_client import MetaWhatsappClient

logger = logging.getLogger(__name__)
TIPO_REPORTE = "SOLICITUD_CHOFER"
MAX_TEXTO = 450


def _texto(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:MAX_TEXTO] or "Sin detalle"


def encolar_reporte(db: AsyncSession, solicitud, datos: tuple) -> None:
    """Agrega las notificaciones a la transacción que guarda el reporte."""
    nombre, dto, detalles = datos
    fallas = [registro[4] for registro in detalles if registro[4]]
    resumen = "; ".join(fallas[:3]) or dto.descripcion_general or "Sin detalle"
    parametros = [_texto(nombre)[:100], _texto(solicitud.n_bus), str(solicitud.id), _texto(resumen)]
    evento = uuid4().hex
    for numero in settings.WHATSAPP_SOLICITUDES_DESTINATARIOS.split(","):
        clave = hashlib.sha256(f"{TIPO_REPORTE}:{evento}:{numero}".encode()).hexdigest()
        db.add(WhatsappEnvio(
            clave=clave, solicitud_id=solicitud.id, tipo=TIPO_REPORTE, severidad="INFO",
            destinatario=numero, mensaje=json.dumps(parametros, ensure_ascii=False),
            estado="PENDIENTE", intentos=1,
        ))


class WhatsappSolicitudesService:
    def __init__(self, sender=None) -> None:
        self.sender = sender or MetaWhatsappClient()
        self.repo = WhatsappRepository()

    async def _reservar(self, db: AsyncSession) -> WhatsappNotificacionDTO | None:
        ahora = datetime.now(timezone.utc)
        candidato = select(WhatsappEnvio.id).where(
            WhatsappEnvio.tipo == TIPO_REPORTE,
            or_(WhatsappEnvio.estado == "PENDIENTE", (WhatsappEnvio.estado == "REINTENTABLE") &
                (WhatsappEnvio.proximo_intento <= ahora) & (WhatsappEnvio.intentos < MAX_INTENTOS)),
        ).order_by(WhatsappEnvio.id).limit(1).scalar_subquery()
        stmt = update(WhatsappEnvio).where(WhatsappEnvio.id == candidato, WhatsappEnvio.estado.in_(["PENDIENTE", "REINTENTABLE"])).values(
            estado="ENVIANDO", updated_at=ahora,
            intentos=WhatsappEnvio.intentos + (WhatsappEnvio.estado == "REINTENTABLE").cast(WhatsappEnvio.intentos.type),
            proximo_intento=None,
        ).returning(WhatsappEnvio)
        registro = (await db.scalars(stmt)).first()
        if registro is None:
            await db.commit()
            return None
        envio = WhatsappNotificacionDTO(
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
        registro = await db.scalar(select(WhatsappEnvio).where(WhatsappEnvio.clave == envio.clave))
        if resultado.estado == "REINTENTABLE" and registro.intentos >= MAX_INTENTOS:
            resultado = WhatsappResultadoDTO(estado="FALLIDO", codigo_error="LIMITE_REINTENTOS")
        await self.repo.registrar_resultado(db, (registro.id, resultado))
        await db.commit()
        return True


whatsapp_solicitudes_service = WhatsappSolicitudesService()


async def ejecutar_timer_solicitudes() -> None:
    while True:
        try:
            async with AsyncSessionLocal() as db:
                procesado = await whatsapp_solicitudes_service.procesar(db)
            if procesado:
                continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[WHATSAPP-SOLICITUDES] Error al procesar cola")
        await asyncio.sleep(settings.WHATSAPP_SOLICITUDES_INTERVAL_SECONDS)
