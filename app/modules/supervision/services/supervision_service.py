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
    ) -> List[SolicitudDTO]:
        logger.info("[SUPERVISION_SERVICE] Obteniendo auditoria de solicitudes | n_bus=%s | estado=%s | mecanico_nombre=%s", n_bus, estado, mecanico_nombre)
        solicitudes = await supervision_repository.get_auditoria(db, n_bus=n_bus, estado=estado, mecanico_nombre=mecanico_nombre)
        return [mantencion_service._to_solicitud_dto(s) for s in solicitudes]

    async def get_resumen_taller(self, db: AsyncSession) -> ResumenTallerDTO:
        logger.info("[SUPERVISION_SERVICE] Calculando resumen y métricas generales del taller con agregaciones SQL")
        
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

        # 2. Consultar únicamente solicitudes activas (estado != 'FINALIZADO') para alertas y buses activos
        solicitudes_activas = await supervision_repository.get_solicitudes_activas(db)
        
        fallas_bloqueadas_por_repuesto = 0
        buses_activos: List[str] = []
        alertas: List[AlertaSupervisionDTO] = []

        for sol in solicitudes_activas:
            if sol.n_bus and sol.n_bus not in buses_activos:
                buses_activos.append(sol.n_bus)

            # Alertas por falta de repuestos en solicitudes activas
            for det in sol.detalles:
                if getattr(det, "falta_repuesto", False):
                    fallas_bloqueadas_por_repuesto += 1
                    alertas.append(
                        AlertaSupervisionDTO(
                            tipo="REPUESTO_FALTANTE",
                            severidad="ALTA",
                            solicitud_id=sol.id,
                            n_bus=sol.n_bus,
                            detalle_id=det.id,
                            mensaje=(
                                f"Falla #{det.id} en Bus {sol.n_bus} detenida por falta de repuestos"
                                + (f": {det.comentario_repuesto}" if det.comentario_repuesto else "")
                            ),
                        )
                    )

            # Alertas por defectos en pauta preventiva en órdenes activas
            if hasattr(sol, "pauta_respuestas") and sol.pauta_respuestas:
                for pr in sol.pauta_respuestas:
                    if pr.estado == "DEFECTO":
                        item_txt = pr.item.item if pr.item else f"Ítem #{pr.item_id}"
                        alertas.append(
                            AlertaSupervisionDTO(
                                tipo="DEFECTO_PAUTA",
                                severidad="MEDIA",
                                solicitud_id=sol.id,
                                n_bus=sol.n_bus,
                                mensaje=f"Ítem de pauta preventiva con defecto en Bus {sol.n_bus}: {item_txt}",
                            )
                        )

            # Alertas por buses en reparación sin mecánicos activos
            if sol.estado == "EN_REPARACION":
                mecs_activos = [m for m in sol.mecanicos if m.is_activo]
                if not mecs_activos:
                    alertas.append(
                        AlertaSupervisionDTO(
                            tipo="BUS_SIN_MECANICOS",
                            severidad="MEDIA",
                            solicitud_id=sol.id,
                            n_bus=sol.n_bus,
                            mensaje=f"Bus {sol.n_bus} figura EN_REPARACION pero no tiene mecánicos activos asignados",
                        )
                    )

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
        """Retorna exclusivamente las alertas operacionales activas de taller."""
        resumen = await self.get_resumen_taller(db)
        return resumen.alertas


supervision_service = SupervisionService()
