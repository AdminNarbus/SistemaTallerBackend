import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.formularios.dtos.pauta_dto import (
    PautaBatchUpdateDTO,
    PautaEstadoResumenDTO,
    PautaRespuestaDTO,
    PautaTallerItemDTO,
)
from app.modules.formularios.repository.pauta_repository import (
    PautaRepository,
    pauta_repository,
)
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario

logger = logging.getLogger(__name__)


class FormularioPautaService:
    """
    Servicio de capa de negocio responsable exclusivamente del checklist preventivo
    de taller (pauta preventiva de 11 ítems estándar).
    """

    def __init__(self, repository: Optional[PautaRepository] = None) -> None:
        self.repo = repository or pauta_repository

    async def get_pauta_items(self, db: AsyncSession) -> List[PautaTallerItemDTO]:
        """Retorna el catálogo maestro de ítems de la pauta preventiva."""
        items = await self.repo.get_pauta_items(db)
        return [PautaTallerItemDTO.model_validate(it) for it in items]

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

        now = datetime.now()

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
            comentario=f"{mec_nom} registró/actualizó {len(dto.respuestas)} ítem(s) de la pauta preventiva",
            fecha_registro=now,
        )
        db.add(comentario_entry)

        await db.commit()
        return await self.get_pauta_resumen(db, solicitud_id)


# Instancia por defecto y alias canónico
formulario_pauta_service = FormularioPautaService()
PautaService = FormularioPautaService
pauta_service = formulario_pauta_service
