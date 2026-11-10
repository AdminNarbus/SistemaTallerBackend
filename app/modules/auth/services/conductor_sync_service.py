import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.realtime.events import RealtimeEvent, publish_event
from app.core.security import get_password_hash, verify_password
from app.core.exceptions import BusinessRuleException
from app.modules.auth.dtos.conductor_sync_dto import ConductorExternoDTO, ConductorSyncResponseDTO
from app.modules.auth.models.conductor_sync import ConductorSync
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.repository.conductor_sync_repository import conductor_sync_repository as repository
from app.modules.auth.services.conductor_source import obtener_conductores
from app.modules.auth.user_cache import clear_user_cache

logger = logging.getLogger(__name__)
CHILE_TIMEZONE = ZoneInfo("America/Santiago")
SYNC_DAY = 6
SYNC_HOUR = 23
SYNC_MINUTE = 59
PASSWORD_DIGITS = 4


def periodo_pendiente(ahora: datetime) -> str:
    local = ahora.astimezone(CHILE_TIMEZONE)
    vencimiento = local.replace(day=SYNC_DAY, hour=SYNC_HOUR, minute=SYNC_MINUTE, second=0, microsecond=0)
    if local < vencimiento:
        local = local.replace(day=1) - timedelta(days=1)
    return local.strftime("%Y-%m")


def aplicar_conductor(usuario: Usuario, conductor: ConductorExternoDTO) -> bool:
    """Se ejecuta en un hilo: bcrypt no debe bloquear el event loop del API."""
    campos = {"username": conductor.rut, "nombre": conductor.nombre,
              "apellido": conductor.apellido or "", "is_active": conductor.activo}
    cambiado = any(getattr(usuario, campo) != valor for campo, valor in campos.items())
    password = conductor.rut[:PASSWORD_DIGITS]
    if not usuario.password_hash or not verify_password(password, usuario.password_hash):
        usuario.password_hash = get_password_hash(password)
        cambiado = True
    for campo, valor in campos.items():
        setattr(usuario, campo, valor)
    return cambiado


class ConductorSyncService:
    async def previsualizar_sincronizacion(
        self, db: AsyncSession, conductores: list[ConductorExternoDTO],
    ) -> ConductorSyncResponseDTO:
        """Calcula los mismos cambios que la aplicación y revierte la transacción."""
        try:
            resultado, _ = await self._aplicar(db, conductores, datetime.now(CHILE_TIMEZONE).strftime("%Y-%m"))
            return resultado
        finally:
            await db.rollback()

    async def sincronizar_ahora(
        self, db: AsyncSession, conductores: list[ConductorExternoDTO],
    ) -> ConductorSyncResponseDTO:
        """Actualiza existentes y crea faltantes sin consumir el calendario mensual."""
        try:
            await repository.bloquear(db)
            resultado, modificados = await self._aplicar(db, conductores, datetime.now(CHILE_TIMEZONE).strftime("%Y-%m"))
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            logger.error("[CONDUCTOR-SYNC] Sincronización revertida | tipo=%s", type(exc).__name__)
            raise BusinessRuleException("La base rechazó la sincronización; no se confirmaron cambios.") from None
        except Exception:
            await db.rollback()
            logger.exception("[CONDUCTOR-SYNC] Sincronización inmediata cancelada")
            raise
        await self._notificar(modificados)
        logger.info("[CONDUCTOR-SYNC] Sincronización inmediata confirmada | resultado=%s", resultado.model_dump())
        return resultado

    async def previsualizar_altas(
        self, db: AsyncSession, conductores: list[ConductorExternoDTO],
    ) -> ConductorSyncResponseDTO:
        existentes = await repository.obtener_usuarios(db, [item.rut for item in conductores])
        return self._resumir_altas(conductores, existentes)

    def _resumir_altas(
        self, conductores: list[ConductorExternoDTO], existentes: dict[str, Usuario],
    ) -> ConductorSyncResponseDTO:
        otros_roles = sum(usuario.rol_rel.nombre != "CONDUCTOR" for usuario in existentes.values())
        return ConductorSyncResponseDTO(
            periodo=datetime.now(CHILE_TIMEZONE).strftime("%Y-%m"),
            recibidos=len(conductores), creados=len(conductores) - len(existentes),
            sin_cambios=len(existentes) - otros_roles, omitidos_otro_rol=otros_roles,
        )

    async def incorporar_nuevos(
        self, db: AsyncSession, conductores: list[ConductorExternoDTO],
    ) -> ConductorSyncResponseDTO:
        """Carga urgente: solo altas, sin consumir la ejecución mensual ni requerir su tabla."""
        try:
            await repository.bloquear(db)
            existentes = await repository.obtener_usuarios(db, [item.rut for item in conductores])
            resultado = self._resumir_altas(conductores, existentes)
            nuevos = [item for item in conductores if item.rut not in existentes]
            if nuevos:
                await self._aplicar(db, nuevos, resultado.periodo)
            await db.commit()
        except SQLAlchemyError as exc:
            await db.rollback()
            # El detalle del motor puede incluir la fila y hashes; no se registra.
            logger.error("[CONDUCTOR-SYNC] Carga revertida por error de persistencia | tipo=%s", type(exc).__name__)
            raise BusinessRuleException("La base rechazó la carga; se revirtieron todas las altas.") from None
        except Exception:
            await db.rollback()
            logger.exception("[CONDUCTOR-SYNC] Carga inmediata cancelada")
            raise
        logger.info("[CONDUCTOR-SYNC] Altas inmediatas confirmadas | resultado=%s", resultado.model_dump())
        return resultado

    async def sincronizar(self, db: AsyncSession) -> ConductorSyncResponseDTO:
        """Actualiza el último mes vencido, con exclusión mutua y commit atómico."""
        periodo = periodo_pendiente(datetime.now(CHILE_TIMEZONE))
        try:
            await repository.bloquear(db)
            anterior = await repository.obtener_ejecucion(db, periodo)
            if anterior:
                resultado = ConductorSyncResponseDTO(**{**anterior.resultado, "estado": "ya_ejecutado"})
                await db.rollback()
                return resultado
            conductores = await obtener_conductores()
            resultado, modificados = await self._aplicar(db, conductores, periodo)
            await repository.guardar(db, ConductorSync(periodo=periodo, resultado=resultado.model_dump()))
        except Exception:
            await db.rollback()
            logger.exception("[CONDUCTOR-SYNC] Sincronización cancelada | periodo=%s", periodo)
            raise
        await self._notificar(modificados)
        logger.info("[CONDUCTOR-SYNC] Finalizada | resultado=%s", resultado.model_dump())
        return resultado

    async def _aplicar(
        self, db: AsyncSession, conductores: list[ConductorExternoDTO], periodo: str,
    ) -> tuple[ConductorSyncResponseDTO, list[Usuario]]:
        rol = await repository.obtener_rol(db)
        existentes = await repository.obtener_usuarios(db, [item.rut for item in conductores])
        resultado = ConductorSyncResponseDTO(periodo=periodo, recibidos=len(conductores))
        modificados = []
        for conductor in conductores:
            usuario = existentes.get(conductor.rut)
            if usuario and usuario.rol_id != rol.id:
                resultado.omitidos_otro_rol += 1
                continue
            nuevo = usuario is None
            if nuevo:
                usuario = Usuario(rol_id=rol.id)
                db.add(usuario)
            estado_anterior = usuario.is_active
            cambiado = await asyncio.to_thread(aplicar_conductor, usuario, conductor)
            if not nuevo and estado_anterior != conductor.activo:
                resultado.habilitados += int(conductor.activo)
                resultado.inhabilitados += int(not conductor.activo)
            if nuevo:
                resultado.creados += 1
            elif cambiado:
                resultado.actualizados += 1
            else:
                resultado.sin_cambios += 1
            if cambiado:
                modificados.append(usuario)
        return resultado, modificados

    async def _notificar(self, usuarios: list[Usuario]) -> None:
        from app.core.realtime.runtime import realtime_runtime

        for usuario in usuarios:
            clear_user_cache(usuario.id)
            await publish_event(RealtimeEvent(
                resource_type="user", resource_id=usuario.id, action="synchronized",
            ))
            if not usuario.is_active:
                await realtime_runtime.disconnect_user(usuario.id)


conductor_sync_service = ConductorSyncService()
