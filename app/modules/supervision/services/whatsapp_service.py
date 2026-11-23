import hashlib
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BusinessRuleException
from app.modules.supervision.constants import SeveridadAlerta
from app.modules.supervision.dtos.supervision_dto import AlertaSupervisionDTO
from app.modules.supervision.dtos.whatsapp_dto import (
    WhatsappEnvioDTO, WhatsappNotificacionDTO, WhatsappResumenDTO, WhatsappResultadoDTO,
)
from app.modules.supervision.repository.whatsapp_repository import MAX_INTENTOS, WhatsappRepository
from app.modules.supervision.services.supervision_service import supervision_service
from app.modules.supervision.services.whatsapp_client import MetaWhatsappClient, WhatsappSender

logger = logging.getLogger(__name__)
SEVERIDADES = tuple(SeveridadAlerta)
MAX_PARAMETRO_LENGTH = 500
CAMPOS_RESULTADO = {
    "ACEPTADO": "aceptados", "FALLIDO": "fallidos", "INCIERTO": "inciertos",
    "REINTENTABLE": "reintentos_pendientes",
}


def construir_notificacion(alerta: AlertaSupervisionDTO, destinatario: str) -> WhatsappNotificacionDTO:
    identidad = f"{alerta.tipo}:{alerta.solicitud_id}:{alerta.detalle_id}:{alerta.severidad}:{destinatario}"
    parametros = [str(alerta.severidad), str(alerta.tipo), alerta.n_bus, str(alerta.solicitud_id), alerta.mensaje]
    return WhatsappNotificacionDTO(
        clave=hashlib.sha256(identidad.encode()).hexdigest(), solicitud_id=alerta.solicitud_id,
        tipo=str(alerta.tipo), severidad=str(alerta.severidad), destinatario=destinatario,
        mensaje=alerta.mensaje,
        parametros=[re.sub(r"\s+", " ", texto).strip()[:MAX_PARAMETRO_LENGTH] or "S/N" for texto in parametros],
    )


class WhatsappAlertasService:
    def __init__(self, repo: WhatsappRepository, sender: WhatsappSender) -> None:
        self.repo = repo
        self.sender = sender

    async def notificar(self, db: AsyncSession) -> WhatsappResumenDTO:
        """Notifica una vez por OT/tipo/detalle/severidad/destinatario.

        La reserva se confirma antes de llamar a Meta para coordinar instancias.
        Solo se reintentan rechazos explícitos por límite de solicitudes (429).
        """
        self._validar_activacion()
        await self.repo.expirar_reservas(db)
        await db.commit()
        alertas = await supervision_service.get_alertas_taller(db)
        await db.commit()
        resumen = WhatsappResumenDTO(alertas_activas=len(alertas))
        for alerta in self._filtrar_alertas(alertas):
            for destinatario in settings.WHATSAPP_DESTINATARIOS.split(","):
                resultado = await self._notificar_destinatario(db, construir_notificacion(alerta, destinatario))
                campo = CAMPOS_RESULTADO[resultado.estado] if resultado else "omitidos"
                setattr(resumen, campo, getattr(resumen, campo) + 1)
        logger.info("[WHATSAPP] Ciclo de alertas completado | resumen=%s", resumen.model_dump())
        return resumen

    async def _notificar_destinatario(
        self, db: AsyncSession, notificacion: WhatsappNotificacionDTO,
    ) -> WhatsappResultadoDTO | None:
        reserva = await self.repo.reservar(db, notificacion)
        await db.commit()
        if reserva is None:
            return None
        envio_id, intentos = reserva
        resultado = await self.sender.enviar(notificacion)
        if resultado.estado == "REINTENTABLE" and intentos >= MAX_INTENTOS:
            resultado = WhatsappResultadoDTO(estado="FALLIDO", codigo_error="LIMITE_REINTENTOS")
        await self.repo.registrar_resultado(db, (envio_id, resultado))
        await db.commit()
        logger.info("[WHATSAPP] Intento registrado | envio_id=%s | estado=%s", envio_id, resultado.estado)
        return resultado

    async def listar(self, db: AsyncSession, pagina: tuple[int, int]) -> list[WhatsappEnvioDTO]:
        """Consulta paginada del historial, incluso con el envío desactivado."""
        return [WhatsappEnvioDTO.model_validate(envio) for envio in await self.repo.listar(db, pagina)]

    @staticmethod
    def _validar_activacion() -> None:
        if not settings.WHATSAPP_ENABLED:
            raise BusinessRuleException("Las notificaciones de WhatsApp están desactivadas")

    @staticmethod
    def _filtrar_alertas(alertas: list[AlertaSupervisionDTO]) -> list[AlertaSupervisionDTO]:
        minimo = SEVERIDADES.index(settings.WHATSAPP_SEVERIDAD_MINIMA)
        return [
            alerta for alerta in alertas
            if alerta.severidad in SEVERIDADES and SEVERIDADES.index(alerta.severidad) >= minimo
        ]


whatsapp_service = WhatsappAlertasService(WhatsappRepository(), MetaWhatsappClient())
