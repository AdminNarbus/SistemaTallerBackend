import json
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.utils import calcular_horas_en_taller
from app.modules.mantencion.services.mantencion_service import (
    MantencionService,
    mantencion_service,
)
from app.modules.mantencion.dtos.mantencion_dto import (
    AsignarFallasSupervisoraDTO,
    CambiarEstadoSolicitudDTO,
    SolicitudDTO,
    AgregarFallaDTO,
    ResolverFallaSupervisoraDTO,
    DetalleUpdateDTO,
)

from app.modules.supervision.constants import (
    DEFAULT_PAGE_SKIP,
    DEFAULT_PAGE_LIMIT,
)
from app.modules.supervision.repository.supervision_repository import (
    SupervisionRepository,
    supervision_repository,
)
from app.modules.supervision.dtos import (
    ResumenTallerDTO,
    AlertaSupervisionDTO,
    MecanicoCargaDTO,
    SolicitudAuditoriaDTO,
    MecanicoAuditoriaDTO,
    DetalleFallaAuditoriaDTO,
)

logger = logging.getLogger(__name__)


class SupervisionService:
    """
    Servicio de capa de negocio para telemetría, auditoría y análisis de rendimiento del taller.
    Aplica Principio de Inversión de Dependencias (DIP) y desacoplamiento de capas.
    """

    def __init__(
        self,
        repository: Optional[SupervisionRepository] = None,
        mantencion_srv: Optional[MantencionService] = None,
    ) -> None:
        self.repo = repository or supervision_repository
        self.mantencion = mantencion_srv or mantencion_service

    def _mapear_a_auditoria_dto(self, item: dict | TallerSolicitud) -> SolicitudAuditoriaDTO:
        if isinstance(item, dict):
            return self._mapear_dict_a_auditoria_dto(item)
        return self._mapear_orm_a_auditoria_dto(item)

    def _mapear_dict_a_auditoria_dto(self, data: dict) -> SolicitudAuditoriaDTO:
        mecanicos_raw = data.get("mecanicos") or data.get("mecanicos_json") or []
        if isinstance(mecanicos_raw, str):
            mecanicos_raw = json.loads(mecanicos_raw)
        mecanicos_dtos = [
            MecanicoAuditoriaDTO(
                mecanico_nombre=m.get("mecanico_nombre", ""),
                is_activo=m.get("is_activo", True),
            )
            for m in mecanicos_raw
            if m.get("mecanico_nombre")
        ]

        detalles_raw = data.get("detalles") or data.get("detalles_json") or []
        if isinstance(detalles_raw, str):
            detalles_raw = json.loads(detalles_raw)
        detalles_dtos = [
            DetalleFallaAuditoriaDTO(
                id=d.get("id"),
                falla_nombre=d.get("falla_nombre"),
                categoria_nombre=d.get("categoria_nombre"),
                descripcion_personalizada=d.get("descripcion_personalizada"),
                resuelto=bool(d.get("resuelto", False)),
                falta_repuesto=bool(d.get("falta_repuesto", False)),
            )
            for d in detalles_raw
        ]

        return SolicitudAuditoriaDTO(
            id=data["id"],
            n_bus=data.get("n_bus") or "S/N",
            estado=data["estado"],
            fecha_creacion=data["fecha_creacion"],
            fecha_cierre=data.get("fecha_cierre"),
            fecha_liberacion=data.get("fecha_liberacion"),
            usuario_creador_nombre=data.get("usuario_creador_nombre"),
            mecanico_cierre_nombre=data.get("mecanico_cierre_nombre"),
            horas_en_taller=data.get("horas_en_taller"),
            reincidencias_30d=data.get("reincidencias_30d", 0) or 0,
            total_fallas=data.get("total_fallas", 0) or 0,
            fallas_resueltas=data.get("fallas_resueltas", 0) or 0,
            fallas_pendientes=data.get("fallas_pendientes", 0) or 0,
            fallas_con_falta_repuesto=data.get("fallas_con_falta_repuesto", 0) or 0,
            mecanicos=mecanicos_dtos,
            detalles=detalles_dtos,
        )

    def _mapear_orm_a_auditoria_dto(self, sol: TallerSolicitud) -> SolicitudAuditoriaDTO:
        mecanicos_dtos: List[MecanicoAuditoriaDTO] = []
        historial_mecs: List[MecanicoAuditoriaDTO] = []
        vistos_activos = set()

        mecanicos_list = list(getattr(sol, "mecanicos", []) or [])
        nuevos_mecs = getattr(sol, "_mecanicos_nuevos", [])
        for nm in nuevos_mecs:
            if nm not in mecanicos_list:
                mecanicos_list.append(nm)

        for sm in mecanicos_list:
            u = getattr(sm, "mecanico", None)
            if u:
                nom = f"{u.nombre} {u.apellido}".strip()
                dto = MecanicoAuditoriaDTO(
                    mecanico_nombre=nom,
                    is_activo=bool(getattr(sm, "is_activo", True)),
                )
                historial_mecs.append(dto)
                if getattr(sm, "is_activo", False) and nom not in vistos_activos:
                    vistos_activos.add(nom)
                    mecanicos_dtos.append(dto)

        # Si la orden está finalizada o no tiene activos, incluir mecánicos únicos históricos
        if not mecanicos_dtos and historial_mecs:
            vistos_fin = set()
            for h in historial_mecs:
                if h.mecanico_nombre not in vistos_fin:
                    vistos_fin.add(h.mecanico_nombre)
                    mecanicos_dtos.append(h)

        detalles_dtos: List[DetalleFallaAuditoriaDTO] = []
        total_fallas = 0
        fallas_resueltas = 0
        fallas_pendientes = 0
        fallas_con_falta_repuesto = 0
        if getattr(sol, "detalles", None):
            total_fallas = len(sol.detalles)
            for d in sol.detalles:
                if d.resuelto:
                    fallas_resueltas += 1
                else:
                    fallas_pendientes += 1
                if d.falta_repuesto:
                    fallas_con_falta_repuesto += 1

                falla_nom = (
                    d.descripcion_personalizada
                    or (d.falla.nombre if getattr(d, "falla", None) else None)
                    or f"Avería #{d.id}"
                )
                cat_nom = (
                    d.falla.categoria.nombre
                    if getattr(d, "falla", None) and getattr(d.falla, "categoria", None)
                    else None
                )
                detalles_dtos.append(
                    DetalleFallaAuditoriaDTO(
                        id=d.id,
                        falla_nombre=falla_nom,
                        categoria_nombre=cat_nom,
                        descripcion_personalizada=d.descripcion_personalizada,
                        resuelto=d.resuelto,
                        falta_repuesto=d.falta_repuesto,
                    )
                )

        creador_nom = None
        if getattr(sol, "creador", None):
            creador_nom = f"{sol.creador.nombre} {sol.creador.apellido}".strip()

        mecanico_cierre_nom = None
        if getattr(sol, "mecanico_cierre", None):
            mecanico_cierre_nom = f"{sol.mecanico_cierre.nombre} {sol.mecanico_cierre.apellido}".strip()

        horas_taller = getattr(sol, "horas_en_taller", None)
        if horas_taller is None and sol.fecha_creacion:
            horas_taller = calcular_horas_en_taller(sol.fecha_creacion, sol.fecha_cierre)

        return SolicitudAuditoriaDTO(
            id=sol.id,
            n_bus=sol.n_bus or "S/N",
            estado=sol.estado,
            fecha_creacion=sol.fecha_creacion,
            fecha_cierre=sol.fecha_cierre,
            fecha_liberacion=sol.fecha_liberacion,
            usuario_creador_nombre=creador_nom,
            mecanico_cierre_nombre=mecanico_cierre_nom,
            horas_en_taller=horas_taller,
            reincidencias_30d=getattr(sol, "reincidencias_30d", 0) or 0,
            total_fallas=total_fallas,
            fallas_resueltas=fallas_resueltas,
            fallas_pendientes=fallas_pendientes,
            fallas_con_falta_repuesto=fallas_con_falta_repuesto,
            mecanicos=mecanicos_dtos,
            detalles=detalles_dtos,
        )

    async def get_auditoria_solicitudes(
        self,
        db: AsyncSession,
        n_bus: Optional[str] = None,
        estado: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
        skip: int = DEFAULT_PAGE_SKIP,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> List[SolicitudAuditoriaDTO]:
        """Obtiene la auditoría de solicitudes de taller optimizada para tarjetas de supervisión."""
        logger.info(
            "[SUPERVISION_SERVICE] Obteniendo auditoria de solicitudes | n_bus=%s | estado=%s | mecanico_nombre=%s | skip=%s | limit=%s",
            n_bus,
            estado,
            mecanico_nombre,
            skip,
            limit,
        )
        solicitudes = await self.repo.get_auditoria(
            db,
            n_bus=n_bus,
            estado=estado,
            mecanico_nombre=mecanico_nombre,
            skip=skip,
            limit=limit,
        )
        return [self._mapear_a_auditoria_dto(item) for item in solicitudes]

    async def count_auditoria_solicitudes(
        self,
        db: AsyncSession,
        n_bus: Optional[str] = None,
        estado: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
    ) -> int:
        """Retorna el conteo total de solicitudes bajo los filtros de auditoría."""
        return await self.repo.count_auditoria(
            db, n_bus=n_bus, estado=estado, mecanico_nombre=mecanico_nombre
        )

    async def get_resumen_taller(self, db: AsyncSession) -> ResumenTallerDTO:
        """Calcula y retorna el resumen consolidado, KPIs y métricas generales del taller."""
        logger.info("[SUPERVISION_SERVICE] Calculando resumen y métricas generales del taller")
        return await self.repo.get_resumen_taller_consolidado(db)

    async def get_alertas_taller(self, db: AsyncSession) -> List[AlertaSupervisionDTO]:
        """Retorna exclusivamente las alertas operacionales activas de taller de forma directa."""
        logger.info("[SUPERVISION_SERVICE] Consultando centro de alertas operacionales activas directamente")
        return await self.repo.get_alertas_activas(db)

    async def get_mecanicos_con_carga(self, db: AsyncSession) -> List[MecanicoCargaDTO]:
        """Retorna la lista de mecánicos activos junto a su conteo de fallas asignadas y disponibilidad."""
        logger.info("[SUPERVISION_SERVICE] Consultando carga y disponibilidad de mecánicos activos")
        raw_rows = await self.repo.get_mecanicos_con_carga(db)
        return [MecanicoCargaDTO(**row) for row in raw_rows]

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
        return await self.mantencion.asignar_fallas_supervisora(
            db, solicitud_id=solicitud_id, dto=dto, supervisor_id=supervisor_id
        )

    async def cambiar_estado_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: CambiarEstadoSolicitudDTO,
        supervisor_id: int,
        supervisor_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        """
        Caso de uso de supervisión: Cambio de estado de una OT por parte de la supervisora
        con justificación en la bitácora inmutable.
        Coordina con MantencionService para la ejecución de las reglas de taller.
        """
        logger.info(
            "[SUPERVISION_SERVICE] Cambiando estado de solicitud | supervisor_id=%s | solicitud_id=%s | nuevo_estado=%s",
            supervisor_id,
            solicitud_id,
            dto.estado.value,
        )
        return await self.mantencion.cambiar_estado_solicitud(
            db,
            solicitud_id=solicitud_id,
            dto=dto,
            supervisor_id=supervisor_id,
            supervisor_nombre=supervisor_nombre,
        )

    async def agregar_falla(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: AgregarFallaDTO,
        supervisor_id: int,
    ) -> SolicitudDTO:
        """Permite a la supervisora agregar una avería a una OT existente."""
        logger.info(
            "[SUPERVISION_SERVICE] Supervisora %s agregando falla a solicitud_id=%s",
            supervisor_id,
            solicitud_id,
        )
        return await self.mantencion.agregar_falla(
            db,
            solicitud_id=solicitud_id,
            mecanico_id=supervisor_id,
            dto=dto,
        )

    async def resolver_falla(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        dto: ResolverFallaSupervisoraDTO,
        supervisor_id: int,
        supervisor_nombre: Optional[str] = None,
    ) -> DetalleUpdateDTO:
        """Permite a la supervisora marcar una falla como resuelta indicando qué mecánico la reparó (o reabrirla)."""
        logger.info(
            "[SUPERVISION_SERVICE] Supervisora %s resolviendo falla detalle_id=%s en solicitud_id=%s | resuelto=%s | mecanico_id=%s",
            supervisor_id,
            detalle_id,
            solicitud_id,
            dto.resuelto,
            dto.mecanico_id,
        )
        return await self.mantencion.resolver_falla_supervisora(
            db,
            solicitud_id=solicitud_id,
            detalle_id=detalle_id,
            dto=dto,
            supervisor_id=supervisor_id,
            supervisor_nombre=supervisor_nombre,
        )

    async def get_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
    ) -> SolicitudDTO:
        """Permite a la supervisora obtener el detalle completo de una OT."""
        logger.info("[SUPERVISION_SERVICE] Consultando solicitud_id=%s", solicitud_id)
        return await self.mantencion.get_solicitud(db, solicitud_id=solicitud_id)


supervision_service = SupervisionService()

