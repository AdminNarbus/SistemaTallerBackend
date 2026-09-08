import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import AsignarFallasSupervisoraDTO, SolicitudDTO
from app.modules.supervision.repository.supervision_repository import supervision_repository
from app.modules.supervision.dtos.supervision_dto import (
    ResumenTallerDTO,
    MetricasEstadoDTO,
    CategoriaFrecuenciaDTO,
    AlertaSupervisionDTO,
)

logger = logging.getLogger(__name__)


class SupervisionService:
    """
    Servicio de capa de negocio para telemetría, auditoría y análisis de rendimiento del taller.
    """

    async def get_auditoria_solicitudes(
        self,
        db: AsyncSession,
        n_bus: Optional[str] = None,
        estado: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[SolicitudDTO]:
        logger.info(
            "[SUPERVISION_SERVICE] Obteniendo auditoria de solicitudes | n_bus=%s | estado=%s | mecanico_nombre=%s | skip=%s | limit=%s",
            n_bus,
            estado,
            mecanico_nombre,
            skip,
            limit,
        )
        solicitudes = await supervision_repository.get_auditoria(
            db, n_bus=n_bus, estado=estado, mecanico_nombre=mecanico_nombre, skip=skip, limit=limit
        )
        return [mantencion_service._to_solicitud_dto(s) for s in solicitudes]

    async def get_resumen_taller(self, db: AsyncSession) -> ResumenTallerDTO:
        logger.info("[SUPERVISION_SERVICE] Calculando resumen y métricas generales del taller con consultas atómicas optimizadas")
        
        # 1. Agregaciones SQL nativas en BD
        conteos_estado = await supervision_repository.get_conteos_por_estado(db)
        total_solicitudes = sum(conteos_estado.values())
        reportadas = conteos_estado.get("REPORTADO", 0)
        pendientes = conteos_estado.get("PENDIENTE", 0)
        en_reparacion = conteos_estado.get("EN_REPARACION", 0)
        pendiente_reasignacion = conteos_estado.get("PENDIENTE_REASIGNACION", 0)
        finalizadas = conteos_estado.get("FINALIZADO", 0)

        buses_en_taller_count = await supervision_repository.get_total_buses_en_taller(db)
        total_fallas, total_resueltas = await supervision_repository.get_conteos_fallas(db)
        fallas_cat_raw = await supervision_repository.get_fallas_por_categoria(db)

        # 2. Consultas atómicas de alertas y buses activos sin carga masiva en memoria
        alertas = await supervision_repository.get_alertas_activas(db)
        buses_activos = await supervision_repository.get_buses_activos_taller(db)
        fallas_bloqueadas_por_repuesto = sum(1 for a in alertas if a.tipo == "REPUESTO_FALTANTE")

        metricas_estado = MetricasEstadoDTO(
            total_solicitudes=total_solicitudes,
            reportadas=reportadas,
            pendientes=pendientes,
            en_reparacion=en_reparacion,
            pendiente_reasignacion=pendiente_reasignacion,
            finalizadas=finalizadas,
            buses_fisicamente_en_taller=buses_en_taller_count,
            fallas_bloqueadas_por_repuesto=fallas_bloqueadas_por_repuesto,
        )

        pct_resolucion = (total_resueltas / total_fallas * 100.0) if total_fallas > 0 else 0.0

        fallas_por_categoria = [
            CategoriaFrecuenciaDTO(
                categoria_id=row[0],
                categoria_nombre=row[1] or "Personalizada / Sin Categoría",
                total_fallas=row[2],
            )
            for row in fallas_cat_raw
        ]
        fallas_por_categoria.sort(key=lambda x: x.total_fallas, reverse=True)

        return ResumenTallerDTO(
            metricas_estado=metricas_estado,
            porcentaje_resolucion_fallas=round(pct_resolucion, 2),
            total_fallas_registradas=total_fallas,
            total_fallas_resueltas=total_resueltas,
            fallas_por_categoria=fallas_por_categoria,
            buses_activos_taller=buses_activos,
            alertas=alertas,
        )

    async def get_alertas_taller(self, db: AsyncSession) -> List[AlertaSupervisionDTO]:
        """Retorna exclusivamente las alertas operacionales activas de taller de forma directa."""
        logger.info("[SUPERVISION_SERVICE] Consultando centro de alertas operacionales activas directamente")
        return await supervision_repository.get_alertas_activas(db)

    async def asignar_fallas_supervisora(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: AsignarFallasSupervisoraDTO,
        supervisor_id: int,
    ) -> SolicitudDTO:
        """
        Caso de uso de supervisión: Asignación directa de fallas por parte de la supervisora
        a un mecánico específico. Coordina con MantencionService para la ejecución de la regla de taller.
        """
        logger.info(
            "[SUPERVISION_SERVICE] Asignando fallas a mecánico | supervisor_id=%s | mecanico_id=%s | solicitud_id=%s",
            supervisor_id,
            dto.mecanico_id,
            solicitud_id,
        )
        return await mantencion_service.asignar_fallas_supervisora(
            db, solicitud_id=solicitud_id, dto=dto, supervisor_id=supervisor_id
        )


supervision_service = SupervisionService()
