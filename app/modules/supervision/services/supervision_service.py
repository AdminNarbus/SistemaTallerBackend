import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import SolicitudDTO
from app.modules.supervision.repository.supervision_repository import supervision_repository
from app.modules.supervision.dtos.supervision_dto import (
    ResumenTallerDTO,
    MetricasEstadoDTO,
    CategoriaFrecuenciaDTO,
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
    ) -> List[SolicitudDTO]:
        logger.info("[SUPERVISION_SERVICE] Obteniendo auditoria de solicitudes | n_bus=%s | estado=%s | mecanico_nombre=%s", n_bus, estado, mecanico_nombre)
        solicitudes = await supervision_repository.get_auditoria(db, n_bus=n_bus, estado=estado, mecanico_nombre=mecanico_nombre)
        return [mantencion_service._to_solicitud_dto(s) for s in solicitudes]

    async def get_resumen_taller(self, db: AsyncSession) -> ResumenTallerDTO:
        logger.info("[SUPERVISION_SERVICE] Calculando resumen y métricas generales del taller")
        solicitudes = await supervision_repository.get_auditoria(db)

        reportadas = sum(1 for s in solicitudes if s.estado == "REPORTADO")
        en_reparacion = sum(1 for s in solicitudes if s.estado == "EN_REPARACION")
        pendiente_reasignacion = sum(1 for s in solicitudes if s.estado == "PENDIENTE_REASIGNACION")
        finalizadas = sum(1 for s in solicitudes if s.estado == "FINALIZADO")

        metricas_estado = MetricasEstadoDTO(
            total_solicitudes=len(solicitudes),
            reportadas=reportadas,
            en_reparacion=en_reparacion,
            pendiente_reasignacion=pendiente_reasignacion,
            finalizadas=finalizadas,
        )

        total_fallas = 0
        total_resueltas = 0
        cat_counts = {}

        buses_activos = []

        for sol in solicitudes:
            if sol.estado != "FINALIZADO" and sol.n_bus not in buses_activos:
                buses_activos.append(sol.n_bus)

            for det in sol.detalles:
                total_fallas += 1
                if det.resuelto:
                    total_resueltas += 1

                cat_nombre = "Personalizada / Sin Categoría"
                cat_id = None
                if det.falla and det.falla.categoria:
                    cat_nombre = det.falla.categoria.nombre
                    cat_id = det.falla.categoria.id

                if cat_nombre not in cat_counts:
                    cat_counts[cat_nombre] = {"id": cat_id, "count": 0}
                cat_counts[cat_nombre]["count"] += 1

        pct_resolucion = (total_resueltas / total_fallas * 100.0) if total_fallas > 0 else 0.0

        fallas_por_categoria = [
            CategoriaFrecuenciaDTO(
                categoria_id=data["id"],
                categoria_nombre=nombre,
                total_fallas=data["count"]
            )
            for nombre, data in cat_counts.items()
        ]
        fallas_por_categoria.sort(key=lambda x: x.total_fallas, reverse=True)

        return ResumenTallerDTO(
            metricas_estado=metricas_estado,
            porcentaje_resolucion_fallas=round(pct_resolucion, 2),
            total_fallas_registradas=total_fallas,
            total_fallas_resueltas=total_resueltas,
            fallas_por_categoria=fallas_por_categoria,
            buses_activos_taller=buses_activos,
        )


supervision_service = SupervisionService()
