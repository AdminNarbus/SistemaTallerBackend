import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.formularios.dtos.pauta_dto import (
    PautaBatchUpdateDTO,
    PautaEstadoResumenDTO,
    PautaRespuestaDTO,
    PautaTallerItemDTO,
    PautaGestionDTO,
    PautaGestionUpdateDTO,
    PautaPuntoDTO,
    PautaProgresoDTO,
)
from app.modules.formularios.repository.pauta_repository import (
    PautaRepository,
    pauta_repository,
)
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.core.realtime.events import RealtimeEvent, publish_event_soon

logger = logging.getLogger(__name__)


class FormularioPautaService:
    """
    Servicio de capa de negocio responsable exclusivamente del checklist preventivo
    de taller (pauta preventiva de 10 ítems estándar).
    """

    def __init__(self, repository: Optional[PautaRepository] = None) -> None:
        self.repo = repository or pauta_repository

    async def get_pauta_items(self, db: AsyncSession) -> List[PautaTallerItemDTO]:
        """Retorna el catálogo maestro de ítems de la pauta preventiva."""
        items = await self.repo.get_pauta_items(db)
        return [PautaTallerItemDTO.model_validate(it) for it in items]

    async def get_progreso(self, db: AsyncSession, solicitud_id: int) -> PautaProgresoDTO:
        return PautaProgresoDTO(**await self.repo.get_progreso(db, solicitud_id))

    async def get_gestion(self, db: AsyncSession, solicitud_id: int) -> PautaGestionDTO:
        if not await self.repo.check_solicitud_exists(db, solicitud_id):
            raise NotFoundException("Solicitud de taller no encontrada")
        items = await self.get_pauta_items(db)
        resumen = await self.get_pauta_resumen(db, solicitud_id)
        respuestas = {respuesta.item_id: respuesta for respuesta in resumen.respuestas}
        return PautaGestionDTO(
            solicitud_id=solicitud_id,
            resumen=PautaProgresoDTO(revisadas=resumen.respondidos, total=resumen.total_items),
            puntos=[PautaPuntoDTO(**item.model_dump(), revisado=item.id in respuestas,
                                 respuesta=respuestas.get(item.id)) for item in items],
        )

    async def actualizar_gestion(
        self, db: AsyncSession, solicitud_id: int, dto: PautaGestionUpdateDTO, actor_id: int,
    ) -> PautaGestionDTO:
        self._validar_cambios(dto)
        if not await self.repo.lock_solicitud(db, solicitud_id):
            raise NotFoundException("Solicitud de taller no encontrada")
        item_ids = [punto.item_id for punto in dto.puntos]
        validos = await self.repo.get_pauta_items_by_ids(db, item_ids)
        if set(item_ids) != validos:
            raise NotFoundException("Uno o más ítems de pauta no existen o están inactivos")
        mecanicos = await self._validar_mecanicos(db, dto)
        now = datetime.now(timezone.utc)
        pendientes = [punto.item_id for punto in dto.puntos if punto.estado is None]
        respuestas = [dict(punto.model_dump(), mecanicos_ids=punto.revisores_ids)
                      for punto in dto.puntos if punto.estado is not None]
        await self.repo.eliminar_respuestas(db, solicitud_id, pendientes)
        await self.repo.upsert_pauta_respuestas(db, solicitud_id, respuestas, actor_id, now)
        await self._registrar_gestion(db, solicitud_id, dto, actor_id, now, mecanicos)
        await db.commit()
        publish_event_soon(RealtimeEvent(resource_type="work_order", resource_id=solicitud_id,
                           action="checklist.changed", actor_id=actor_id, version=now))
        return await self.get_gestion(db, solicitud_id)

    @staticmethod
    def _validar_cambios(dto: PautaGestionUpdateDTO) -> None:
        item_ids = [punto.item_id for punto in dto.puntos]
        if len(item_ids) != len(set(item_ids)):
            raise BusinessRuleException("No se puede repetir un ítem en la misma actualización")
        if any(punto.estado is None and punto.observacion is not None for punto in dto.puntos):
            raise BusinessRuleException("Un punto pendiente no admite observación de revisión")
        for punto in dto.puntos:
            FormularioPautaService._validar_revisores(punto)

    @staticmethod
    def _validar_revisores(punto) -> None:
        if punto.mecanicos_ids is not None and punto.mecanico_id is not None:
            raise BusinessRuleException("Use mecanicos_ids o mecanico_id, no ambos")
        ids = punto.revisores_ids
        if len(ids) != len(set(ids)) or any(revisor <= 0 for revisor in ids):
            raise BusinessRuleException("Los IDs de mecánicos deben ser positivos y no repetidos")
        if punto.estado is not None and not ids:
            raise BusinessRuleException("Debe indicar uno o más mecánicos para cada revisión")
        if punto.estado is None and ids:
            raise BusinessRuleException("Un punto pendiente no admite mecánicos revisores")

    async def _validar_mecanicos(self, db: AsyncSession, dto: PautaGestionUpdateDTO) -> dict[int, str]:
        ids = {revisor for punto in dto.puntos for revisor in punto.revisores_ids}
        if not ids:
            return {}
        mecanicos = await self.repo.get_mecanicos_activos(db, ids)
        if set(mecanicos) != ids:
            raise BusinessRuleException("Los revisores deben ser usuarios MECANICO activos")
        return mecanicos

    async def _registrar_gestion(
        self, db: AsyncSession, solicitud_id: int, dto: PautaGestionUpdateDTO,
        actor_id: int, now: datetime, mecanicos: dict[int, str],
    ) -> None:
        cambios = "; ".join(
            f"ítem {punto.item_id}: {punto.estado.value if punto.estado else 'PENDIENTE'}"
            + ("; revisores: " + ", ".join(f"{mecanicos[revisor]} (ID {revisor})"
                                          for revisor in punto.revisores_ids)
               if punto.revisores_ids else "")
            + (f" ({punto.observacion})" if punto.observacion else "")
            for punto in dto.puntos
        )
        comentario = TallerSolicitudComentario(
            solicitud_id=solicitud_id, usuario_id=actor_id, tipo="CHECKLIST",
            comentario=f"Pauta supervisión: {cambios}", fecha_registro=now,
        )
        await self.repo.registrar_gestion(db, comentario)
        logger.info("[PAUTA] Gestión supervisión | solicitud_id=%s | actor_id=%s | %s",
                    solicitud_id, actor_id, cambios)

    async def get_pauta_resumen(
        self, db: AsyncSession, solicitud_id: int
    ) -> PautaEstadoResumenDTO:
        """Calcula el estado de completitud, ítems respondidos, pendientes y con defecto."""
        total_items, respuestas = await self.repo.get_pauta_resumen(db, solicitud_id)

        resp_dtos = [PautaRespuestaDTO(**r) for r in respuestas]
        defectos_count = sum(1 for r in respuestas if r["estado"] == "DEFECTO")
        respondidos = len(resp_dtos)
        pendientes = max(0, total_items - respondidos)

        return PautaEstadoResumenDTO(
            total_items=total_items,
            respondidos=respondidos,
            pendientes=pendientes,
            completado=respondidos >= total_items and total_items > 0,
            items_con_defecto=defectos_count,
            respuestas=resp_dtos,
        )

    async def guardar_respuestas_pauta(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: PautaBatchUpdateDTO,
        mecanico_id: int,
    ) -> PautaEstadoResumenDTO:
        """Registra o actualiza en lote respuestas a los ítems de la pauta preventiva de manera atómica."""
        logger.info(
            "[PAUTA] Guardando respuestas de pauta | solicitud_id=%s, total_respuestas=%s",
            solicitud_id,
            len(dto.respuestas),
        )
        if not dto.respuestas:
            raise BusinessRuleException("Debe enviar al menos una respuesta de pauta")

        if not await self.repo.lock_solicitud(db, solicitud_id):
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now(timezone.utc)

        # 1. Validar existencia de solicitud, obtener datos del mecánico y verificar ítems
        item_ids = [r.item_id for r in dto.respuestas]
        valid_item_ids = await self.repo.get_pauta_items_by_ids(db, item_ids)
        total_p, resp_p, mec_nom, sol_existe = await self.repo.get_conteo_pauta_y_mecanico(
            db, solicitud_id, mecanico_id
        )
        if not sol_existe:
            raise NotFoundException("Solicitud de taller no encontrada")

        for r_dto in dto.respuestas:
            if r_dto.item_id not in valid_item_ids:
                raise NotFoundException(f"Ítem de pauta con ID {r_dto.item_id} no existe")

        mec_nom = mec_nom or "Mecánico"

        # 2. Guardar o actualizar en lote (1 sola operación atómica ON CONFLICT DO UPDATE)
        respuestas_data = [r.model_dump() for r in dto.respuestas]
        await self.repo.upsert_pauta_respuestas(
            db, solicitud_id, respuestas_data, mecanico_id, now
        )

        # 3. Registrar comentario de bitácora
        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud_id,
            usuario_id=mecanico_id,
            tipo="CHECKLIST",
            comentario=f"Pauta: {len(dto.respuestas)} ítem(s)",
            fecha_registro=now,
        )
        db.add(comentario_entry)
        await db.execute(
            update(TallerSolicitud)
            .where(TallerSolicitud.id == solicitud_id)
            .values(fecha_actualizacion=now)
        )

        await db.commit()
        result = await self.get_pauta_resumen(db, solicitud_id)
        publish_event_soon(RealtimeEvent(
            resource_type="work_order",
            resource_id=solicitud_id,
            action="checklist.changed",
            actor_id=mecanico_id,
            version=now,
        ))
        return result


# Instancia por defecto y alias canónico
formulario_pauta_service = FormularioPautaService()
PautaService = FormularioPautaService
pauta_service = formulario_pauta_service
