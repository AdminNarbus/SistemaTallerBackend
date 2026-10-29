import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NarbusException, NotFoundException
from app.core.realtime.events import RealtimeEvent, publish_event_soon
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.buses.models.bus import Bus
from app.modules.taller.dtos.averias_dto import AgregarFallaDTO
from app.modules.taller.dtos.bus_mecanico_dto import (
    AgregarFallaBusDTO, BusesMecanicoFiltroDTO, BusMecanicoDTO, OTBusMecanicoDTO,
)
from app.modules.taller.dtos.solicitud_dto import SolicitudDTO
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.repository.buses_taller_repository import BusesTallerRepository
from app.modules.taller.repository.taller_repository import TallerRepository, taller_repository
from app.modules.taller.services.averias_service import AveriasService
from app.modules.taller.services.mappers import orm_to_solicitud_dto
from app.modules.taller.services.trazabilidad_estados import RegistroEstadoOT, registrar_evento_estado

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegistroFallaBus:
    bus_id: int
    actor: UsuarioResponseDTO
    falla: AgregarFallaBusDTO


class BusesTallerService:
    def __init__(
        self, repository: BusesTallerRepository | None = None,
        taller_repo: TallerRepository | None = None, averias: AveriasService | None = None,
    ) -> None:
        self.repo = repository or BusesTallerRepository()
        self.taller_repo = taller_repo or taller_repository
        self.averias = averias or AveriasService(self.taller_repo)

    async def listar(self, db: AsyncSession, filtros: BusesMecanicoFiltroDTO) -> tuple[list[BusMecanicoDTO], int]:
        parametros = filtros.model_dump()
        parametros["q"] = (filtros.q or "").strip()
        filas = await self.repo.listar(db, parametros)
        buses = [self._mapear_bus(fila) for fila in filas if fila["bus_id"] is not None]
        return buses, int(filas[0]["total"]) if filas else 0

    def _mapear_bus(self, fila: dict) -> BusMecanicoDTO:
        ot = None
        if fila["ot_id"] is not None:
            ot = OTBusMecanicoDTO(
                id=fila["ot_id"], estado=fila["ot_estado"],
                fecha_actualizacion=fila["fecha_actualizacion"],
                numero_fallas_pendientes=fila["numero_fallas_pendientes"],
            )
        return BusMecanicoDTO(**{campo: fila[campo] for campo in (
            "bus_id", "n_bus", "patente", "marca", "modelo", "en_taller", "is_active",
        )}, ot=ot)

    async def agregar_falla(self, db: AsyncSession, registro: RegistroFallaBus) -> SolicitudDTO:
        try:
            solicitud, es_nueva = await self._registrar_falla(db, registro)
            await self.taller_repo.flush(db)
            resultado = orm_to_solicitud_dto(solicitud)
            await db.commit()
        except NarbusException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            logger.exception("Error registrando falla de bus | bus_id=%s | actor_id=%s", registro.bus_id, registro.actor.id)
            raise
        publish_event_soon(RealtimeEvent(
            resource_type="work_order", resource_id=resultado.id,
            action="created" if es_nueva else "updated", actor_id=registro.actor.id,
            version=resultado.fecha_actualizacion,
        ))
        return resultado

    async def _registrar_falla(self, db: AsyncSession, registro: RegistroFallaBus) -> tuple[TallerSolicitud, bool]:
        if not registro.falla.texto_falla and not registro.falla.falla_id:
            raise BusinessRuleException("Debe indicar el nombre o descripción de la avería a agregar")
        bus = await self._obtener_bus(db, registro.bus_id)
        await self._validar_catalogo(db, registro.falla)
        solicitud = await self._resolver_ot(db, bus)
        es_nueva = solicitud is None
        if es_nueva:
            solicitud = await self._crear_ot(db, bus, registro.actor)
        payload = self._payload_falla(registro)
        solicitud = await self.averias.registrar_falla(db, solicitud.id, registro.actor.id, payload)
        logger.info("Falla registrada desde bus | bus_id=%s | ot_id=%s | nueva_ot=%s | autoasignar=%s",
                    bus.id, solicitud.id, es_nueva, registro.falla.autoasignar)
        return solicitud, es_nueva

    async def _obtener_bus(self, db: AsyncSession, bus_id: int) -> Bus:
        bus = await self.taller_repo.get_bus_by_id(db, bus_id)
        if bus is None:
            raise NotFoundException("El bus indicado no existe")
        if not bus.is_active:
            raise BusinessRuleException("No se pueden reportar fallas a un bus dado de baja")
        return bus

    async def _resolver_ot(self, db: AsyncSession, bus: Bus) -> TallerSolicitud | None:
        solicitud = await self.taller_repo.get_solicitud_activa_por_bus(db, bus.id, bus.n_bus)
        if solicitud is None and bus.n_bus:
            solicitud = await self.taller_repo.get_solicitud_activa_por_bus(db, None, bus.n_bus)
            if solicitud is not None:
                solicitud.bus_id = bus.id
                await self.taller_repo.flush(db)
        return solicitud

    async def _validar_catalogo(self, db: AsyncSession, falla: AgregarFallaBusDTO) -> None:
        if falla.falla_id is not None:
            catalogo = await self.taller_repo.get_falla_by_id(db, falla.falla_id)
            if catalogo is None or not catalogo.is_active:
                raise BusinessRuleException("La falla de catálogo indicada no existe o está inactiva")
            if falla.categoria_id is not None and catalogo.categoria_id != falla.categoria_id:
                raise BusinessRuleException("La falla indicada no pertenece a la categoría seleccionada")
        if falla.categoria_id is not None:
            categoria = await self.taller_repo.get_categoria_by_id(db, falla.categoria_id)
            if categoria is None or not categoria.is_active:
                raise BusinessRuleException("La categoría indicada no existe o está inactiva")

    async def _crear_ot(self, db: AsyncSession, bus: Bus, actor: UsuarioResponseDTO) -> TallerSolicitud:
        now = datetime.now(timezone.utc)
        solicitud = TallerSolicitud(
            bus_id=bus.id, n_bus=bus.n_bus or str(bus.id), usuario_creador_id=actor.id,
            estado="PENDIENTE", fecha_creacion=now, fecha_actualizacion=now,
            horas_taller_acumuladas=0,
        )
        self.taller_repo.add_solicitud(db, solicitud)
        await self.taller_repo.flush(db)
        await registrar_evento_estado(db, RegistroEstadoOT(
            solicitud_id=solicitud.id, estado_anterior=None, estado_nuevo="PENDIENTE",
            actor_id=actor.id, actor_nombre=actor.nombre_completo, fecha_evento=now,
            tipo_evento="CREACION", motivo="Reporte de falla desde el bus",
        ))
        return solicitud

    def _payload_falla(self, registro: RegistroFallaBus) -> AgregarFallaDTO:
        payload = AgregarFallaDTO(
            **registro.falla.model_dump(exclude={"categoria_nombre"}),
        )
        if not payload.descripcion_personalizada:
            payload.descripcion_personalizada = registro.falla.texto_falla or None
        if registro.falla.autoasignar and registro.actor.rol == "ADMIN":
            payload.mecanico_asignado_id = registro.actor.id
        return payload


buses_taller_service = BusesTallerService()
