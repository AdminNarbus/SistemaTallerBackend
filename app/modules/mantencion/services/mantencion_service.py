import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.core.storage.storage_service import storage_service
from app.modules.auth.constants import RolUsuario
from app.modules.mantencion.constants import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_PAGE_SKIP,
    MAX_PAGE_LIMIT,
    TOTAL_ITEMS_PAUTA_PREVENTIVA,
    EstadoSolicitud,
    OrigenAsignacion,
    TipoComentarioBitacora,
)
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.mantencion.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.mantencion.models.pauta_taller import TallerSolicitudPauta
from app.modules.mantencion.models.taller_solicitud_evidencia import TallerSolicitudEvidencia
from app.modules.mantencion.repository.mantencion_repository import (
    MantencionRepository,
    mantencion_repository,
)
from app.modules.mantencion.utils import (
    calcular_duracion_minutos,
    describir_detalle_averia,
    formatear_comentario_cierre,
    recopilar_archivos_fotos,
    validar_fallas_cierre_parcial,
    validar_pauta_preventiva_cierre,
)
from app.modules.mantencion.dtos import (
    CategoriaFallaDTO,
    FallaTallerDTO,
    SolicitudDTO,
    SolicitudResumenDTO,
    SolicitudEvidenciaDTO,
    SolicitudDetalleDTO,
    SolicitudMecanicoDTO,
    SolicitudComentarioDTO,
    SolicitudCreateDTO,
    TomarTrabajoDTO,
    LiberarTurnoDTO,
    FinalizarSolicitudDTO,
    ComentarioCreateDTO,
    AgregarColaboradorDTO,
    MecanicoAsignadoDTO,
    AsignacionFallaDTO,
    AutoasignarFallasDTO,
    AsignarFallasSupervisoraDTO,
    CambiarEstadoSolicitudDTO,
    TerminarAvanceDTO,

    ReportarRepuestoDTO,
    PautaTallerItemDTO,
    PautaRespuestaDTO,
    PautaBatchUpdateDTO,
    PautaEstadoResumenDTO,
    LiberarSolicitudDTO,
    AgregarFallaDTO,
    DetalleUpdateDTO,
    ComentarioAddedDTO,
    ResolverFallaSupervisoraDTO,
)

logger = logging.getLogger(__name__)

# Re-exportaciones para interoperabilidad hacia atrás
_describir_detalle = describir_detalle_averia
_calcular_duracion_minutos = calcular_duracion_minutos


class MantencionService:
    """
    Capa de servicio de negocio / Casos de Uso para el módulo de Taller de Mantención.
    Responsabilidad exclusiva: Validaciones de reglas operacionales, orquestación de pasos,
    transformación a DTOs y control transaccional (commit/rollback).
    Soporta inyección de dependencias para testing unitario aislado.
    """

    def __init__(
        self,
        repository: Optional[MantencionRepository] = None,
        storage: Optional[Any] = None,
    ) -> None:
        self.repo = repository or mantencion_repository
        self.storage = storage or storage_service


    def _attach_comentario_safe(self, solicitud, comentario, usuario_nombre: Optional[str] = None) -> None:
        if usuario_nombre:
            comentario._usuario_nombre_cached = usuario_nombre
        if "comentarios" in getattr(solicitud, "__dict__", {}) and solicitud.__dict__["comentarios"] is not None:
            solicitud.__dict__["comentarios"].append(comentario)
        else:
            if not hasattr(solicitud, "_comentarios_nuevos") or solicitud._comentarios_nuevos is None:
                solicitud._comentarios_nuevos = []
            solicitud._comentarios_nuevos.append(comentario)

    def _attach_mecanico_safe(self, solicitud, mecanico) -> None:
        if "mecanicos" in getattr(solicitud, "__dict__", {}) and solicitud.__dict__["mecanicos"] is not None:
            solicitud.__dict__["mecanicos"].append(mecanico)
        else:
            if not hasattr(solicitud, "_mecanicos_nuevos") or solicitud._mecanicos_nuevos is None:
                solicitud._mecanicos_nuevos = []
            solicitud._mecanicos_nuevos.append(mecanico)

    def mapear_a_solicitud_dto(self, item: Any) -> Optional[SolicitudDTO]:
        """
        Mapea de forma segura un diccionario agregado (PostgreSQL JSON) o un modelo ORM (SQLite) a SolicitudDTO.
        Punto de entrada público que encapsula las conversiones internas.
        """
        if item is None:
            return None
        if isinstance(item, dict):
            return self._dict_to_solicitud_dto(item)
        return self._to_solicitud_dto(item)

    def _to_solicitud_dto(self, sol) -> Optional[SolicitudDTO]:
        if not sol:
            return None

        def _get_rel(obj, attr: str):
            """Obtiene una relación cargada desde __dict__ sin disparar lazy loading síncrono."""
            if obj is None:
                return None
            return getattr(obj, "__dict__", {}).get(attr)

        detalles_dtos = []
        detalles_list = _get_rel(sol, "detalles") or []
        for det in detalles_list:
            falla_dto = None
            cat_id = None
            cat_nombre = None
            falla_obj = _get_rel(det, "falla")
            if falla_obj:
                cat_dto = None
                cat_obj = _get_rel(falla_obj, "categoria")
                if cat_obj:
                    cat_id = cat_obj.id
                    cat_nombre = cat_obj.nombre
                    cat_dto = CategoriaFallaDTO(
                        id=cat_obj.id,
                        nombre=cat_obj.nombre,
                        is_active=cat_obj.is_active,
                    )
                falla_dto = FallaTallerDTO(
                    id=falla_obj.id,
                    categoria_id=falla_obj.categoria_id,
                    nombre=falla_obj.nombre,
                    is_active=falla_obj.is_active,
                    categoria=cat_dto,
                )

            mec_resolvio = _get_rel(det, "mecanico_resolvio")
            mec_resolvio_nombre = mec_resolvio.nombre_completo if mec_resolvio else None
            if not mec_resolvio_nombre and det.mecanico_resolvio_id:
                for asig_item in getattr(det, "asignaciones", []) or []:
                    asig_u = _get_rel(asig_item, "mecanico")
                    if asig_u and asig_u.id == det.mecanico_resolvio_id:
                        mec_resolvio_nombre = asig_u.nombre_completo
                        break
                if not mec_resolvio_nombre:
                    for mec_item in getattr(sol, "mecanicos", []) or []:
                        u_m = _get_rel(mec_item, "mecanico")
                        if u_m and u_m.id == det.mecanico_resolvio_id:
                            mec_resolvio_nombre = u_m.nombre_completo
                            break

            mecanicos_asignados = []
            historial_asignaciones = []
            mecs_asig_vistos = set()
            asignaciones_list = _get_rel(det, "asignaciones") or []
            for asig in asignaciones_list:
                asig_mec = _get_rel(asig, "mecanico")
                mec_nom = asig_mec.nombre_completo if asig_mec else None
                asig_por = _get_rel(asig, "asignado_por")
                asig_por_nom = asig_por.nombre_completo if asig_por else None

                asig_dto = AsignacionFallaDTO(
                    id=asig.id,
                    solicitud_id=asig.solicitud_id,
                    detalle_id=asig.detalle_id,
                    mecanico_id=asig.mecanico_id,
                    mecanico_nombre=mec_nom,
                    asignado_por_id=asig.asignado_por_id,
                    asignado_por_nombre=asig_por_nom,
                    origen=asig.origen,
                    is_activo=asig.is_activo,
                    fecha_asignacion=asig.fecha_asignacion,
                    fecha_desasignacion=asig.fecha_desasignacion,
                    resuelto_en_esta_asignacion=asig.resuelto_en_esta_asignacion,
                    duracion_minutos=asig.duracion_minutos,
                    comentario=asig.comentario,
                )
                historial_asignaciones.append(asig_dto)
                if asig.is_activo and asig.mecanico_id not in mecs_asig_vistos:
                    mecs_asig_vistos.add(asig.mecanico_id)
                    mecanicos_asignados.append(
                        MecanicoAsignadoDTO(
                            id=asig.mecanico_id,
                            nombre=mec_nom or f"Mecánico #{asig.mecanico_id}",
                            origen=asig.origen,
                            asignado_por_id=asig.asignado_por_id,
                            asignado_por_nombre=asig_por_nom,
                            fecha_asignacion=asig.fecha_asignacion,
                        )
                    )

            detalles_dtos.append(
                SolicitudDetalleDTO(
                    id=det.id,
                    solicitud_id=det.solicitud_id,
                    categoria_id=cat_id,
                    categoria_nombre=cat_nombre,
                    falla_id=det.falla_id,
                    falla=falla_dto,
                    descripcion_personalizada=det.descripcion_personalizada,
                    resuelto=det.resuelto,
                    mecanico_resolvio_id=det.mecanico_resolvio_id,
                    mecanico_resolvio_nombre=mec_resolvio_nombre,
                    falta_repuesto=getattr(det, "falta_repuesto", False) or False,
                    comentario_repuesto=getattr(det, "comentario_repuesto", None),
                    fecha_creacion=det.fecha_creacion,
                    fecha_resolucion=det.fecha_resolucion,
                    mecanicos_asignados=mecanicos_asignados,
                    historial_asignaciones=historial_asignaciones,
                )
            )

        mecanicos_dtos = []
        historial_mecanicos_dtos = []
        mecanicos_activos_ids = set()

        mecanicos_list = list(_get_rel(sol, "mecanicos") or [])
        nuevos_mecs = getattr(sol, "_mecanicos_nuevos", [])
        for nm in nuevos_mecs:
            if nm not in mecanicos_list:
                mecanicos_list.append(nm)
        for mec in mecanicos_list:
            mec_u = _get_rel(mec, "mecanico")
            mec_nombre = mec_u.nombre_completo if mec_u else None

            dto_mec = SolicitudMecanicoDTO(
                id=mec.id,
                solicitud_id=mec.solicitud_id,
                mecanico_id=mec.mecanico_id,
                mecanico_nombre=mec_nombre,
                asignado_por_id=getattr(mec, "asignado_por_id", None),
                duracion_minutos=getattr(mec, "duracion_minutos", None),
                es_lider_responsable=mec.es_lider_responsable,
                is_activo=mec.is_activo,
                fecha_asignacion=mec.fecha_asignacion,
                fecha_desasignacion=mec.fecha_desasignacion,
            )
            historial_mecanicos_dtos.append(dto_mec)

            if getattr(mec, "is_activo", False):
                if mec.mecanico_id not in mecanicos_activos_ids:
                    mecanicos_activos_ids.add(mec.mecanico_id)
                    mecanicos_dtos.append(dto_mec)

        # Consolidar mecánicos con asignaciones de fallas activas si no estuviesen ya registrados
        for det in detalles_list:
            det_asigs = _get_rel(det, "asignaciones") or []
            for asig in det_asigs:
                if getattr(asig, "is_activo", False) and asig.mecanico_id not in mecanicos_activos_ids:
                    mecanicos_activos_ids.add(asig.mecanico_id)
                    asig_mec = _get_rel(asig, "mecanico")
                    mec_nom = asig_mec.nombre_completo if asig_mec else None
                    mecanicos_dtos.append(
                        SolicitudMecanicoDTO(
                            id=asig.id,
                            solicitud_id=sol.id,
                            mecanico_id=asig.mecanico_id,
                            mecanico_nombre=mec_nom,
                            asignado_por_id=asig.asignado_por_id,
                            duracion_minutos=asig.duracion_minutos,
                            es_lider_responsable=False,
                            is_activo=True,
                            fecha_asignacion=asig.fecha_asignacion,
                            fecha_desasignacion=asig.fecha_desasignacion,
                        )
                    )

        # En caso de solicitud FINALIZADA sin activos, incluir mecánicos únicos históricos
        if sol.estado == "FINALIZADO" and not mecanicos_dtos and historial_mecanicos_dtos:
            vistos_fin = set()
            for h_mec in historial_mecanicos_dtos:
                if h_mec.mecanico_id not in vistos_fin:
                    vistos_fin.add(h_mec.mecanico_id)
                    mecanicos_dtos.append(h_mec)

        comentarios_dtos = []
        comentarios_val = list(_get_rel(sol, "comentarios") or [])
        nuevos_coms = getattr(sol, "_comentarios_nuevos", [])
        for nc in nuevos_coms:
            if nc not in comentarios_val:
                comentarios_val.append(nc)
        for com in comentarios_val:
            usr = _get_rel(com, "usuario")
            usr_nombre = usr.nombre_completo if usr else getattr(com, "_usuario_nombre_cached", None)

            comentarios_dtos.append(
                SolicitudComentarioDTO(
                    id=com.id,
                    solicitud_id=com.solicitud_id,
                    usuario_id=com.usuario_id,
                    usuario_nombre=usr_nombre,
                    tipo=com.tipo,
                    comentario=com.comentario,
                    fecha_registro=com.fecha_registro,
                )
            )

        pauta_dtos = []
        pauta_val = _get_rel(sol, "pauta_respuestas") or []
        for pr in pauta_val:
            item_obj = _get_rel(pr, "item")
            item_cat = item_obj.categoria if item_obj else None
            item_nom = item_obj.item if item_obj else None
            pr_mec = _get_rel(pr, "mecanico")
            mec_nom = pr_mec.nombre_completo if pr_mec else None
            pauta_dtos.append(
                PautaRespuestaDTO(
                    id=pr.id,
                    solicitud_id=pr.solicitud_id,
                    item_id=pr.item_id,
                    item_categoria=item_cat,
                    item_nombre=item_nom,
                    estado=pr.estado,
                    observacion=pr.observacion,
                    mecanico_id=pr.mecanico_id,
                    mecanico_nombre=mec_nom,
                    fecha_registro=pr.fecha_registro,
                )
            )

        creador = _get_rel(sol, "creador")
        creador_nombre = creador.nombre_completo if creador else None
        mec_cierre = _get_rel(sol, "mecanico_cierre")
        mecanico_cierre_nombre = (
            mec_cierre.nombre_completo
            if mec_cierre
            else getattr(sol, "_mecanico_cierre_nombre_cached", None)
        )
        bus_obj = _get_rel(sol, "bus")
        bus_patente = bus_obj.patente if bus_obj else None

        total_fallas = len(detalles_dtos)
        fallas_resueltas = len([d for d in detalles_dtos if d.resuelto])
        fallas_con_falta_repuesto = len([d for d in detalles_dtos if d.falta_repuesto])

        evidencias_dtos = []
        evidencias_val = _get_rel(sol, "evidencias") or []
        for ev in evidencias_val:
            evidencias_dtos.append(
                SolicitudEvidenciaDTO(
                    id=ev.id,
                    solicitud_id=ev.solicitud_id,
                    detalle_id=ev.detalle_id,
                    usuario_id=ev.usuario_id,
                    url=self.storage.get_url(ev.url) or ev.url,
                    original_filename=ev.original_filename,
                    size_bytes=ev.size_bytes,
                    content_type=ev.content_type,
                    fecha_creacion=ev.fecha_creacion,
                )
            )

        return SolicitudDTO(
            id=sol.id,
            n_bus=sol.n_bus,
            bus_id=sol.bus_id,
            bus_patente=bus_patente,
            usuario_creador_id=sol.usuario_creador_id,
            usuario_creador_nombre=creador_nombre,
            mecanico_cierre_id=sol.mecanico_cierre_id,
            mecanico_cierre_nombre=mecanico_cierre_nombre,
            estado=sol.estado,
            descripcion_general=sol.descripcion_general,
            foto_url=self.storage.get_url(sol.foto_url),
            motivo_incompleto_checklist=getattr(sol, "motivo_incompleto_checklist", None),
            motivo_cierre_parcial=getattr(sol, "motivo_cierre_parcial", None),
            fecha_creacion=sol.fecha_creacion,
            fecha_cierre=sol.fecha_cierre,
            fecha_liberacion=getattr(sol, "fecha_liberacion", None),
            horas_en_taller=round((((sol.fecha_cierre or datetime.now(sol.fecha_creacion.tzinfo if hasattr(sol.fecha_creacion, "tzinfo") else None)) - sol.fecha_creacion).total_seconds() / 3600), 1) if sol.fecha_creacion else None,
            reincidencias_30d=getattr(sol, "reincidencias_30d", 0),
            pauta_completada=len(pauta_dtos) >= TOTAL_ITEMS_PAUTA_PREVENTIVA,
            total_fallas=total_fallas,
            fallas_resueltas=fallas_resueltas,
            fallas_con_falta_repuesto=fallas_con_falta_repuesto,
            detalles=detalles_dtos,
            mecanicos=mecanicos_dtos,
            historial_mecanicos=historial_mecanicos_dtos,
            comentarios=comentarios_dtos,
            pauta_respuestas=pauta_dtos,
            evidencias=evidencias_dtos,
        )

    # --- Consultas de Catálogos ---

    async def get_categorias(self, db: AsyncSession) -> List[CategoriaFallaDTO]:
        cats = await self.repo.get_categorias_con_fallas(db)
        return [CategoriaFallaDTO(**c) for c in cats]

    async def get_fallas(self, db: AsyncSession, categoria_id: Optional[int] = None) -> List[FallaTallerDTO]:
        fallas = await self.repo.get_fallas(db, categoria_id)
        res = []
        for f in fallas:
            cat_dto = None
            if f.categoria:
                cat_dto = CategoriaFallaDTO(
                    id=f.categoria.id,
                    nombre=f.categoria.nombre,
                    is_active=f.categoria.is_active,
                    falla_id=f.id,
                    falla_nombre=f.nombre,
                )
            res.append(FallaTallerDTO(id=f.id, categoria_id=f.categoria_id, nombre=f.nombre, is_active=f.is_active, categoria=cat_dto))
        return res

    async def get_solicitud(self, db: AsyncSession, solicitud_id: int) -> SolicitudDTO:
        logger.debug("[MANTENCION] Consultando solicitud | id=%s", solicitud_id)
        sol = await self.repo.get_solicitud_dto_by_id(db, solicitud_id)
        if not sol:
            raise NotFoundException("Solicitud de taller no encontrada")
        if isinstance(sol, dict):
            return self._dict_to_solicitud_dto(sol)
        return self._to_solicitud_dto(sol)

    def _parse_evidencias_dtos(self, evidencias_raw: Any) -> List[SolicitudEvidenciaDTO]:
        """Parsea la lista de evidencias (dict o JSON) y genera las Signed URLs correspondientes."""
        if not evidencias_raw:
            return []
        if isinstance(evidencias_raw, str):
            try:
                evidencias_raw = json.loads(evidencias_raw)
            except Exception:
                return []
        if not isinstance(evidencias_raw, list):
            return []

        dtos: List[SolicitudEvidenciaDTO] = []
        for ev in evidencias_raw:
            if not isinstance(ev, dict):
                continue
            raw_url = ev.get("url") or ""
            signed_url = self.storage.get_url(raw_url) or raw_url
            dtos.append(
                SolicitudEvidenciaDTO(
                    id=ev.get("id") or 0,
                    solicitud_id=ev.get("solicitud_id") or 0,
                    detalle_id=ev.get("detalle_id"),
                    usuario_id=ev.get("usuario_id"),
                    url=signed_url,
                    original_filename=ev.get("original_filename"),
                    size_bytes=ev.get("size_bytes"),
                    content_type=ev.get("content_type"),
                    fecha_creacion=ev.get("fecha_creacion"),
                )
            )
        return dtos

    def _dict_to_solicitud_dto(self, r: dict) -> SolicitudDTO:
        """Convierte una fila de detalle de alta velocidad (1 sola consulta SQL CTE) a SolicitudDTO."""
        detalles_raw = r.get("detalles_json") or []
        if isinstance(detalles_raw, str):
            detalles_raw = json.loads(detalles_raw)
        mecanicos_raw = r.get("mecanicos_json") or []
        if isinstance(mecanicos_raw, str):
            mecanicos_raw = json.loads(mecanicos_raw)
        historial_mecanicos_raw = r.get("historial_mecanicos_json") or []
        if isinstance(historial_mecanicos_raw, str):
            historial_mecanicos_raw = json.loads(historial_mecanicos_raw)
        comentarios_raw = r.get("comentarios_json") or []
        if isinstance(comentarios_raw, str):
            comentarios_raw = json.loads(comentarios_raw)
        pauta_respuestas_raw = r.get("pauta_respuestas_json") or []
        if isinstance(pauta_respuestas_raw, str):
            pauta_respuestas_raw = json.loads(pauta_respuestas_raw)
        evidencias_dtos = self._parse_evidencias_dtos(r.get("evidencias_json"))

        tot = len(detalles_raw)
        resueltos = sum(1 for d in detalles_raw if d.get("resuelto"))
        faltas = sum(1 for d in detalles_raw if d.get("falta_repuesto"))
        pauta_completada = len(pauta_respuestas_raw) >= TOTAL_ITEMS_PAUTA_PREVENTIVA

        if r.get("estado") == "FINALIZADO" and not mecanicos_raw and historial_mecanicos_raw:
            vistos_fin = set()
            for h in historial_mecanicos_raw:
                m_id = h.get("mecanico_id")
                if m_id not in vistos_fin:
                    vistos_fin.add(m_id)
                    mecanicos_raw.append(h)

        return SolicitudDTO(
            id=r["id"],
            n_bus=r["n_bus"],
            bus_id=r.get("bus_id"),
            bus_patente=r.get("bus_patente"),
            usuario_creador_id=r.get("usuario_creador_id"),
            usuario_creador_nombre=r.get("usuario_creador_nombre"),
            mecanico_cierre_id=r.get("mecanico_cierre_id"),
            mecanico_cierre_nombre=r.get("mecanico_cierre_nombre"),
            estado=r["estado"],
            descripcion_general=r.get("descripcion_general"),
            foto_url=self.storage.get_url(r.get("foto_url")),
            motivo_incompleto_checklist=r.get("motivo_incompleto_checklist"),
            motivo_cierre_parcial=r.get("motivo_cierre_parcial"),
            fecha_creacion=r["fecha_creacion"],
            fecha_cierre=r.get("fecha_cierre"),
            fecha_liberacion=r.get("fecha_liberacion"),
            horas_en_taller=r.get("horas_en_taller"),
            reincidencias_30d=r.get("reincidencias_30d", 0),
            pauta_completada=pauta_completada,
            total_fallas=tot,
            fallas_resueltas=resueltos,
            fallas_con_falta_repuesto=faltas,
            detalles=detalles_raw,
            mecanicos=mecanicos_raw,
            historial_mecanicos=historial_mecanicos_raw,
            comentarios=comentarios_raw,
            pauta_respuestas=pauta_respuestas_raw,
            evidencias=evidencias_dtos,
        )

    def _dict_to_solicitud_resumen_dto(self, r: dict) -> SolicitudResumenDTO:
        """Convierte una fila del listado de alta velocidad (1 sola consulta SQL) directamente a SolicitudResumenDTO."""
        detalles_raw = r.get("detalles_json") or []
        if isinstance(detalles_raw, str):
            detalles_raw = json.loads(detalles_raw)
        mecanicos_raw = r.get("mecanicos_json") or []
        if isinstance(mecanicos_raw, str):
            mecanicos_raw = json.loads(mecanicos_raw)
        evidencias_dtos = self._parse_evidencias_dtos(r.get("evidencias_json"))

        tot = len(detalles_raw)
        resueltos = sum(1 for d in detalles_raw if d.get("resuelto"))
        faltas = sum(1 for d in detalles_raw if d.get("falta_repuesto"))

        return SolicitudResumenDTO(
            id=r["id"],
            n_bus=r["n_bus"],
            bus_id=r.get("bus_id"),
            bus_patente=r.get("bus_patente"),
            usuario_creador_id=r.get("usuario_creador_id"),
            usuario_creador_nombre=r.get("usuario_creador_nombre"),
            mecanico_cierre_id=r.get("mecanico_cierre_id"),
            mecanico_cierre_nombre=r.get("mecanico_cierre_nombre"),
            estado=r["estado"],
            descripcion_general=r.get("descripcion_general"),
            foto_url=self.storage.get_url(r.get("foto_url")),
            motivo_incompleto_checklist=r.get("motivo_incompleto_checklist"),
            motivo_cierre_parcial=r.get("motivo_cierre_parcial"),
            fecha_creacion=r["fecha_creacion"],
            fecha_cierre=r.get("fecha_cierre"),
            pauta_completada=False,
            total_fallas=tot,
            fallas_resueltas=resueltos,
            fallas_con_falta_repuesto=faltas,
            detalles=detalles_raw,
            mecanicos=mecanicos_raw,
            historial_mecanicos=[],
            comentarios=[],
            pauta_respuestas=[],
            evidencias=evidencias_dtos,
        )

    async def list_pendientes(
        self, db: AsyncSession, limit: Optional[int] = DEFAULT_PAGE_LIMIT, skip: int = DEFAULT_PAGE_SKIP
    ) -> List[SolicitudResumenDTO]:
        logger.debug("[MANTENCION] Listando solicitudes pendientes | limit=%s | skip=%s", limit, skip)
        solicitudes = await self.repo.list_pendientes(db, limit=limit, skip=skip)
        results = []
        for s in solicitudes:
            if isinstance(s, dict):
                results.append(self._dict_to_solicitud_resumen_dto(s))
            else:
                results.append(SolicitudResumenDTO.model_validate(self._to_solicitud_dto(s)))
        return results

    async def count_pendientes(self, db: AsyncSession) -> int:
        """Retorna el conteo total de solicitudes pendientes en taller."""
        return await self.repo.count_pendientes(db)

    async def list_mis_trabajos(
        self, db: AsyncSession, mecanico_id: int, limit: Optional[int] = DEFAULT_PAGE_LIMIT, skip: int = DEFAULT_PAGE_SKIP
    ) -> List[SolicitudResumenDTO]:
        logger.debug("[MANTENCION] Listando trabajos activos | mecanico_id=%s, limit=%s, skip=%s", mecanico_id, limit, skip)
        solicitudes = await self.repo.list_mis_trabajos(db, mecanico_id, limit=limit, skip=skip)
        results = []
        for s in solicitudes:
            if isinstance(s, dict):
                results.append(self._dict_to_solicitud_resumen_dto(s))
            else:
                results.append(SolicitudResumenDTO.model_validate(self._to_solicitud_dto(s)))
        return results

    async def count_mis_trabajos(self, db: AsyncSession, mecanico_id: int) -> int:
        """Retorna el conteo total de trabajos activos del mecánico."""
        return await self.repo.count_mis_trabajos(db, mecanico_id=mecanico_id)


    async def list_auditoria(self, db: AsyncSession) -> List[SolicitudDTO]:
        logger.debug("[MANTENCION] Consultando auditoría completa de solicitudes")
        solicitudes = await self.repo.list_auditoria(db)
        return [self._to_solicitud_dto(s) for s in solicitudes]

    # --- Casos de Uso Operacionales y Transaccionales ---

    async def create_solicitud(
        self,
        db: AsyncSession,
        dto: SolicitudCreateDTO,
        creador_id: int,
        creador_nombre: Optional[str] = None,
        creador_rol: Optional[str] = None,
        foto: Optional[UploadFile] = None,
        fotos: Optional[List[UploadFile]] = None,
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Creando solicitud | n_bus='%s' | bus_id=%s | creador_id=%s | rol=%s", dto.n_bus, dto.bus_id, creador_id, creador_rol)

        # Recopilar y deduplicar evidencias fotográficas recibidas
        archivos_fotos = recopilar_archivos_fotos(foto=foto, fotos=fotos)

        # Subir archivos a almacenamiento configurado (GCS o Local)
        uploaded_evidencias: List[dict] = []
        for f in archivos_fotos:
            upload_res = await self.storage.upload_image(file=f, folder="solicitudes")
            uploaded_evidencias.append(upload_res)
            logger.info(
                "[MANTENCION] Evidencia de solicitud subida | path='%s' | url='%s' | tamano=%s bytes",
                upload_res.get("path"),
                upload_res.get("url"),
                upload_res.get("size_bytes"),
            )

        # Si el cliente envió fotos_urls predefinidas vía JSON
        if dto.fotos_urls:
            for u in dto.fotos_urls:
                if u and not any(e.get("path") == u or e.get("url") == u for e in uploaded_evidencias):
                    uploaded_evidencias.append({
                        "path": u,
                        "url": self.storage.get_url(u) or u,
                        "original_filename": None,
                        "size_bytes": None,
                        "content_type": None,
                    })

        # Asignar foto principal para retrocompatibilidad con frontend
        if uploaded_evidencias and not dto.foto_url:
            dto.foto_url = uploaded_evidencias[0].get("path") or uploaded_evidencias[0]["url"]
        elif dto.foto_url and not any(e.get("path") == dto.foto_url or e.get("url") == dto.foto_url for e in uploaded_evidencias):
            uploaded_evidencias.insert(0, {
                "path": dto.foto_url,
                "url": self.storage.get_url(dto.foto_url) or dto.foto_url,
                "original_filename": None,
                "size_bytes": None,
                "content_type": None,
            })

        # 1. Resolver bus_id y patente
        bus_id = dto.bus_id
        bus_patente = dto.bus_patente
        n_bus = dto.n_bus
        bus_obj = None

        # Optimización: Si el frontend ya envió bus_id y n_bus, no consultamos la tabla 'buses' inicialmente
        if bus_id and n_bus:
            logger.debug("[MANTENCION] Bus resuelto directamente desde frontend | bus_id=%s, n_bus='%s'", bus_id, n_bus)
        elif dto.n_bus:
            bus_info = await self.repo.get_bus_info_by_n_bus(db, dto.n_bus)
            if bus_info:
                bus_id, bus_patente = bus_info
        elif bus_id:
            bus_obj = await self.repo.get_bus_by_id(db, bus_id)
            if bus_obj:
                bus_patente = bus_obj.patente
                n_bus = bus_obj.n_bus

        # 2. Creador de la solicitud (reutiliza el nombre/rol inyectado por auth o consulta en BD)
        if not creador_nombre or not creador_rol:
            u_creador = await self.repo.get_usuario_by_id(db, creador_id)
            if u_creador:
                creador_nombre = creador_nombre or u_creador.nombre_completo
                if not creador_rol:
                    creador_rol = getattr(getattr(u_creador, "rol_rel", None), "nombre", None) or "CONDUCTOR"

        now = datetime.now()
        solicitud = TallerSolicitud(
            n_bus=n_bus or (dto.n_bus if dto.n_bus else str(bus_id)),
            bus_id=bus_id,
            usuario_creador_id=creador_id,
            estado=EstadoSolicitud.REPORTADO.value,
            descripcion_general=dto.descripcion_general,
            foto_url=dto.foto_url,
            fecha_creacion=now,
        )

        # 3. Marcar bus físicamente en taller si lo crea supervisora/admin o si se solicita ingreso inmediato
        rol_upper = (creador_rol or "").upper().strip()
        debe_marcar_en_taller = False
        if dto.ingreso_inmediato_taller is True:
            debe_marcar_en_taller = True
        elif dto.ingreso_inmediato_taller is None and rol_upper in [
            RolUsuario.SUPERVISOR.value,
            RolUsuario.ADMIN.value,
        ]:
            debe_marcar_en_taller = True

        if debe_marcar_en_taller and bus_id:
            if not bus_obj:
                bus_obj = await self.repo.get_bus_by_id(db, bus_id)
            if bus_obj:
                bus_obj.en_taller = True
                solicitud.bus = bus_obj
                logger.info(
                    "[MANTENCION] Bus id=%s (n_bus='%s') marcado en taller físico (en_taller=True) al crear solicitud por %s (rol=%s)",
                    bus_id,
                    solicitud.n_bus,
                    creador_nombre,
                    creador_rol,
                )

        evidencias_a_procesar: List[TallerSolicitudEvidencia] = []
        for ev_data in uploaded_evidencias:
            db_path = ev_data.get("path") or ev_data["url"]
            ev_obj = TallerSolicitudEvidencia(
                usuario_id=creador_id,
                url=db_path,
                original_filename=ev_data.get("original_filename"),
                size_bytes=ev_data.get("size_bytes"),
                content_type=ev_data.get("content_type"),
                fecha_creacion=now,
            )
            solicitud.evidencias.append(ev_obj)
            evidencias_a_procesar.append(ev_obj)

        # 3. Resolución batch y vinculación de detalles en memoria (0 flushes)
        detalles_dtos: List[SolicitudDetalleDTO] = []
        detalles_a_procesar = []
        if dto.detalles:
            # Solo consultar fallas_map para detalles legados SIN falla_id pero CON categoria_id
            needed_cats = [d.categoria_id for d in dto.detalles if not d.falla_id and d.categoria_id]
            fallas_map = await self.repo.find_fallas_activas_by_categorias(db, needed_cats) if needed_cats else {}

            for det_dto in dto.detalles:
                falla_id = det_dto.falla_id
                cat_id = det_dto.categoria_id
                falla_nombre = getattr(det_dto, "falla_nombre", None)
                cat_nombre_res = getattr(det_dto, "categoria_nombre", None)

                if not falla_id and cat_id:
                    if cat_id in fallas_map:
                        falla_id, falla_nombre, cat_nombre_res = fallas_map[cat_id]
                    else:
                        cat = await self.repo.get_categoria_by_id(db, cat_id)
                        cat_nom = cat.nombre if cat else f"Categoría #{cat_id}"
                        cat_nombre_res = cat_nom
                        nueva_falla = FallaTaller(
                            categoria_id=cat_id,
                            nombre=f"Avería de {cat_nom}",
                            is_active=True,
                        )
                        self.repo.add_falla(db, nueva_falla)
                        await self.repo.flush(db)
                        falla_id = nueva_falla.id
                        falla_nombre = nueva_falla.nombre

                detalle = TallerSolicitudDetalle(
                    falla_id=falla_id,
                    descripcion_personalizada=det_dto.descripcion_personalizada,
                    resuelto=False,
                    fecha_creacion=now,
                )
                solicitud.detalles.append(detalle)
                detalles_a_procesar.append((detalle, det_dto, falla_id, cat_id, falla_nombre, cat_nombre_res))

        self.repo.add_solicitud(db, solicitud)
        # UN ÚNICO VIAJE A LA BD: Commit atómico que inserta solicitud y todos sus detalles
        await db.commit()

        # 4. Construir DTOs directamente en memoria tras el commit (con IDs generadas por el commit)
        if detalles_a_procesar:
            for detalle, det_dto, falla_id, cat_id, falla_nombre, cat_nombre_res in detalles_a_procesar:
                falla_dto = None
                cat_dto = None

                cat_nom_final = getattr(det_dto, "categoria_nombre", None) or cat_nombre_res or (f"Categoría #{cat_id}" if cat_id else None)
                if cat_id:
                    cat_dto = CategoriaFallaDTO(
                        id=cat_id,
                        nombre=cat_nom_final or f"Categoría #{cat_id}",
                        is_active=True,
                        falla_id=falla_id,
                        falla_nombre=falla_nombre,
                    )

                if falla_id:
                    falla_nom_final = (
                        getattr(det_dto, "falla_nombre", None)
                        or falla_nombre
                        or det_dto.descripcion_personalizada
                        or f"Avería #{falla_id}"
                    )
                    falla_dto = FallaTallerDTO(
                        id=falla_id,
                        categoria_id=cat_id or 1,
                        nombre=falla_nom_final,
                        is_active=True,
                        categoria=cat_dto,
                    )
                cat_nombre = cat_dto.nombre if cat_dto else None
                detalles_dtos.append(
                    SolicitudDetalleDTO(
                        id=detalle.id,
                        solicitud_id=solicitud.id,
                        categoria_id=cat_id or (falla_dto.categoria_id if falla_dto else 1),
                        categoria_nombre=cat_nombre,
                        falla_id=falla_id,
                        falla=falla_dto,
                        descripcion_personalizada=det_dto.descripcion_personalizada,
                        resuelto=False,
                        falta_repuesto=False,
                        comentario_repuesto=None,
                        fecha_creacion=now,
                        fecha_resolucion=None,
                        mecanico_resolvio_id=None,
                        mecanico_resolvio_nombre=None,
                        mecanicos_asignados=[],
                        historial_asignaciones=[],
                    )
                )

        logger.info("[MANTENCION] Solicitud creada exitosamente | id=%s | n_bus='%s' | estado=REPORTADO", solicitud.id, solicitud.n_bus)

        # 4. Retornar DTO directamente construido en memoria sin disparar 15 consultas selectinload a tablas vacías
        evidencias_dtos = [
            SolicitudEvidenciaDTO(
                id=ev.id,
                solicitud_id=solicitud.id,
                detalle_id=ev.detalle_id,
                usuario_id=ev.usuario_id,
                url=self.storage.get_url(ev.url) or ev.url,
                original_filename=ev.original_filename,
                size_bytes=ev.size_bytes,
                content_type=ev.content_type,
                fecha_creacion=ev.fecha_creacion,
            )
            for ev in evidencias_a_procesar
        ]

        return SolicitudDTO(
            id=solicitud.id,
            n_bus=solicitud.n_bus,
            bus_id=solicitud.bus_id,
            bus_patente=bus_patente,
            usuario_creador_id=solicitud.usuario_creador_id,
            usuario_creador_nombre=creador_nombre,
            mecanico_cierre_id=None,
            mecanico_cierre_nombre=None,
            estado=solicitud.estado,
            descripcion_general=solicitud.descripcion_general,
            foto_url=self.storage.get_url(solicitud.foto_url),
            motivo_incompleto_checklist=None,
            motivo_cierre_parcial=None,
            fecha_creacion=solicitud.fecha_creacion,
            fecha_cierre=None,
            pauta_completada=False,
            total_fallas=len(detalles_dtos),
            fallas_resueltas=0,
            fallas_con_falta_repuesto=0,
            detalles=detalles_dtos,
            mecanicos=[],
            historial_mecanicos=[],
            comentarios=[],
            pauta_respuestas=[],
            evidencias=evidencias_dtos,
        )

    async def tomar_trabajo(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: int, dto: TomarTrabajoDTO
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Tomar trabajo | solicitud_id=%s | mecanico_id=%s | colaboradores=%s", solicitud_id, mecanico_id, dto.colaboradores_ids)
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        # 1. Marcar mecánicos previos como inactivos de forma atómica en el repositorio y en memoria
        await self.repo.desactivar_mecanicos_activos(
            db, solicitud_id=solicitud.id, fecha_desasignacion=now
        )
        if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
            for m in solicitud.mecanicos:
                if getattr(m, "is_activo", False):
                    m.is_activo = False
                    m.fecha_desasignacion = now

        # 2. Batch users resolution (mecanico_id + colaboradores)
        from app.modules.auth.repository.user_repository import user_repository
        target_colab_ids = set(dto.colaboradores_ids or [])
        if dto.colaboradores_nombres:
            colab_users = await user_repository.get_mecanicos_by_nombres_o_usernames(db, dto.colaboradores_nombres)
            for u in colab_users:
                target_colab_ids.add(u.id)

        all_user_ids = [mecanico_id] + [cid for cid in target_colab_ids if cid != mecanico_id]
        users_map = await user_repository.get_by_ids_map(db, all_user_ids)
        u_mec = users_map.get(mecanico_id)
        mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"

        # 3. Asignar mecánico que toma el trabajo (co-responsabilidad horizontal)
        mecanico_entry = TallerSolicitudMecanico(
            solicitud_id=solicitud.id,
            mecanico_id=mecanico_id,
            es_lider_responsable=False,
            is_activo=True,
            fecha_asignacion=now,
        )
        if u_mec:
            mecanico_entry.mecanico = u_mec
        self.repo.add_mecanico(db, mecanico_entry)
        self._attach_mecanico_safe(solicitud, mecanico_entry)
        logger.info("[MANTENCION] Mecánico asignado a solicitud | solicitud_id=%s | mecanico_id=%s", solicitud_id, mecanico_id)

        # 4. Asignar colaboradores
        colab_nombres = []
        for colab_id in target_colab_ids:
            if colab_id != mecanico_id:
                u_c = users_map.get(colab_id)
                if u_c:
                    colab_nombres.append(u_c.nombre_completo)
                colab_entry = TallerSolicitudMecanico(
                    solicitud_id=solicitud.id,
                    mecanico_id=colab_id,
                    es_lider_responsable=False,
                    is_activo=True,
                    fecha_asignacion=now,
                )
                if u_c:
                    colab_entry.mecanico = u_c
                self.repo.add_mecanico(db, colab_entry)
                self._attach_mecanico_safe(solicitud, colab_entry)
                logger.info("[MANTENCION] Colaborador co-responsable asignado | solicitud_id=%s | colab_id=%s", solicitud_id, colab_id)

        # 5. Actualizar estado
        solicitud.estado = "EN_REPARACION"

        # 6. Agregar comentario predeterminado de inicio/asignación
        fallas_nombres = [_describir_detalle(d) for d in (solicitud.detalles or [])]
        if fallas_nombres:
            fallas_str = ", ".join(fallas_nombres)
            texto_inicio = f"{mec_nom} inició los trabajos de esta OT atendiendo las fallas: {fallas_str}"
        else:
            texto_inicio = f"{mec_nom} inició los trabajos de esta OT"

        if colab_nombres:
            texto_inicio += f", junto al equipo: {', '.join(colab_nombres)}"

        if dto.comentario_inicial and dto.comentario_inicial.strip():
            texto_inicio += f". Nota: {dto.comentario_inicial.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="ASIGNACION",
            comentario=texto_inicio,
            fecha_registro=now,
        )
        if u_mec:
            comentario_entry.usuario = u_mec
        self.repo.add_comentario(db, comentario_entry)
        self._attach_comentario_safe(solicitud, comentario_entry, mec_nom)

        await db.commit()
        logger.info("[MANTENCION] Solicitud en reparación | id=%s | estado=EN_REPARACION", solicitud.id)
        return self._to_solicitud_dto(solicitud)

    async def agregar_colaborador(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: int, dto: AgregarColaboradorDTO
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Agregando colaborador en caliente | solicitud_id=%s | solicitado_por=%s", solicitud_id, mecanico_id)
        from app.modules.auth.repository.user_repository import user_repository

        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if solicitud.estado != "EN_REPARACION":
            raise BusinessRuleException("Solo se pueden agregar colaboradores cuando la solicitud está EN_REPARACION")

        mecanico_activo = any(
            m.mecanico_id == mecanico_id and m.is_activo
            for m in solicitud.mecanicos
        )
        if not mecanico_activo:
            raise BusinessRuleException("Solo un mecánico asignado activamente a la solicitud puede agregar colaboradores")

        colab_id = dto.colaborador_id
        if not colab_id and dto.colaborador_nombre:
            encontrados = await user_repository.get_mecanicos_by_nombres_o_usernames(
                db, [dto.colaborador_nombre]
            )
            if not encontrados:
                raise NotFoundException(f"No se encontró un mecánico con nombre '{dto.colaborador_nombre}'")
            colab_id = encontrados[0].id

        if not colab_id:
            raise BusinessRuleException("Debes indicar el ID o nombre del colaborador a agregar")

        if colab_id == mecanico_id:
            raise BusinessRuleException("Un mecánico no puede agregarse a sí mismo como colaborador")

        ya_activo = any(m.mecanico_id == colab_id and m.is_activo for m in solicitud.mecanicos)
        if ya_activo:
            raise BusinessRuleException("El mecánico ya está activo en esta solicitud")

        colab_entry = TallerSolicitudMecanico(
            solicitud_id=solicitud.id,
            mecanico_id=colab_id,
            es_lider_responsable=False,
            is_activo=True,
            fecha_asignacion=datetime.now(),
        )
        u_colab = await user_repository.get_by_id(db, colab_id)
        if u_colab:
            colab_entry.mecanico = u_colab
        self.repo.add_mecanico(db, colab_entry)
        self._attach_mecanico_safe(solicitud, colab_entry)

        await db.commit()
        return self._to_solicitud_dto(solicitud)

    async def desasignar_mecanico(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        comentario: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Desasignando mecánico | solicitud_id=%s | mecanico_id=%s", solicitud_id, mecanico_id)
        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()
        mecs_desactivados = await self.repo.desactivar_mecanicos_por_ids(
            db, solicitud_id=solicitud.id, mecanicos_ids={mecanico_id}, fecha_desasignacion=now
        )
        if not mecs_desactivados:
            logger.warning("[MANTENCION] Desasignación fallida: mecánico no activo | solicitud_id=%s | mecanico_id=%s", solicitud_id, mecanico_id)
            raise BusinessRuleException("El mecánico no está asignado activamente a esta solicitud")

        await self.repo.desactivar_asignaciones_por_mecanicos(
            db, solicitud_id=solicitud.id, mecanicos_ids={mecanico_id}, fecha_desasignacion=now
        )

        if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
            for m in solicitud.mecanicos:
                if m.mecanico_id == mecanico_id and getattr(m, "is_activo", False):
                    m.is_activo = False
                    m.fecha_desasignacion = now
                    if m.fecha_asignacion:
                        m.duracion_minutos = calcular_duracion_minutos(m.fecha_asignacion, now)

        if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas:
            for asig in solicitud.asignaciones_fallas:
                if asig.mecanico_id == mecanico_id and getattr(asig, "is_activo", False):
                    asig.is_activo = False
                    asig.fecha_desasignacion = now
                    if asig.fecha_asignacion:
                        asig.duracion_minutos = calcular_duracion_minutos(asig.fecha_asignacion, now)

        if mecanico_nombre:
            mec_nom = mecanico_nombre
            u_mec = None
        else:
            u_mec = await self.repo.get_usuario_by_id(db, mecanico_id)
            mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"

        texto_desasig = f"{mec_nom} se retiró de los trabajos de la OT"
        if comentario and comentario.strip():
            texto_desasig += f". Motivo: {comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="SALIDA_MECANICO",
            comentario=texto_desasig,
            fecha_registro=now,
        )
        if u_mec:
            comentario_entry.usuario = u_mec
        self.repo.add_comentario(db, comentario_entry)
        self._attach_comentario_safe(solicitud, comentario_entry, mec_nom)

        presencias_activas = await self.repo.get_presencias_activas(db, solicitud_id=solicitud.id)
        if not presencias_activas:
            solicitud.estado = EstadoSolicitud.PENDIENTE.value
            logger.info("[MANTENCION] Sin mecánicos activos → PENDIENTE | solicitud_id=%s", solicitud_id)

        await db.commit()
        return self._to_solicitud_dto(solicitud)

    async def liberar_turno(
        self,
        db: AsyncSession,
        solicitud_id: int,
        usuario_id: int,
        dto: LiberarTurnoDTO,
        usuario_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Liberar turno | solicitud_id=%s | usuario_id=%s", solicitud_id, usuario_id)
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()
        await self.repo.desactivar_cuadrilla_y_asignaciones_completas(
            db, solicitud_id=solicitud.id, fecha_desasignacion=now
        )
        if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
            for m in solicitud.mecanicos:
                if getattr(m, "is_activo", False):
                    m.is_activo = False
                    m.fecha_desasignacion = now
                    if m.fecha_asignacion:
                        m.duracion_minutos = calcular_duracion_minutos(m.fecha_asignacion, now)

        if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas:
            for asig in solicitud.asignaciones_fallas:
                if getattr(asig, "is_activo", False):
                    asig.is_activo = False
                    asig.fecha_desasignacion = now
                    if asig.fecha_asignacion:
                        asig.duracion_minutos = calcular_duracion_minutos(asig.fecha_asignacion, now)

        solicitud.estado = EstadoSolicitud.PENDIENTE.value

        if usuario_nombre:
            usr_nom = usuario_nombre
            u_usr = None
        else:
            u_usr = await self.repo.get_usuario_by_id(db, usuario_id)
            usr_nom = u_usr.nombre_completo if u_usr else "Usuario"

        texto_liberar = f"{usr_nom} entregó y liberó su turno de trabajo en la OT"
        if dto.comentario and dto.comentario.strip():
            texto_liberar += f". Observación: {dto.comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=usuario_id,
            tipo="ENTREGA_TURNO",
            comentario=texto_liberar,
            fecha_registro=now,
        )
        if u_usr:
            comentario_entry.usuario = u_usr
        self.repo.add_comentario(db, comentario_entry)
        self._attach_comentario_safe(solicitud, comentario_entry, usr_nom)

        await db.commit()
        return self._to_solicitud_dto(solicitud)

    async def check_detalle(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        mecanico_id: int,
        resuelto: bool,
        mecanico_nombre: Optional[str] = None,
        mecanico_resolvio_id: Optional[int] = None,
    ) -> DetalleUpdateDTO:
        logger.info(
            "[MANTENCION] Check detalle atómico | solicitud_id=%s | detalle_id=%s | usuario_id=%s | resuelto=%s | mecanico_resolvio_id=%s",
            solicitud_id,
            detalle_id,
            mecanico_id,
            resuelto,
            mecanico_resolvio_id,
        )
        detalle_target = await self.repo.get_detalle_operacional(db, solicitud_id, detalle_id)
        if not detalle_target:
            if not await self.repo.check_solicitud_exists(db, solicitud_id):
                raise NotFoundException("Solicitud de taller no encontrada")
            raise NotFoundException("Detalle de falla no encontrado")

        if resuelto and getattr(detalle_target, "falta_repuesto", False):
            raise BusinessRuleException(
                "No se puede marcar como resuelta una falla que se encuentra a la espera de repuesto. "
                "Debe registrarse primero la recepción/disponibilidad del repuesto."
            )

        now = datetime.now()
        detalle_target.resuelto = resuelto

        # Resolver usuario resolutor efectivo
        resolutor_id = mecanico_resolvio_id if (mecanico_resolvio_id and resuelto) else (mecanico_id if resuelto else None)

        if not mecanico_nombre:
            u_mec = await self.repo.get_usuario_by_id(db, mecanico_id)
            actor_nom = u_mec.nombre_completo if u_mec else "Mecánico"
        else:
            u_mec = None
            actor_nom = mecanico_nombre

        u_resolutor = None
        resolutor_nom = actor_nom
        if resolutor_id and resolutor_id != mecanico_id:
            u_resolutor = await self.repo.get_usuario_by_id(db, resolutor_id)
            if not u_resolutor or not u_resolutor.is_active:
                raise BusinessRuleException("El mecánico resolutor indicado no existe o se encuentra inactivo")
            resolutor_nom = u_resolutor.nombre_completo
        elif u_mec:
            u_resolutor = u_mec

        if resuelto:
            detalle_target.mecanico_resolvio_id = resolutor_id
            detalle_target.fecha_resolucion = now
            if u_resolutor:
                detalle_target.mecanico_resolvio = u_resolutor
        else:
            detalle_target.mecanico_resolvio_id = None
            detalle_target.mecanico_resolvio = None
            detalle_target.fecha_resolucion = None

        db.add(detalle_target)

        falla_nom = _describir_detalle(detalle_target)

        if resuelto:
            if resolutor_id != mecanico_id:
                texto_check = f"{actor_nom} registró la reparación de la falla '{falla_nom}' por el mecánico {resolutor_nom}"
            else:
                texto_check = f"{resolutor_nom} completó la reparación de la falla: '{falla_nom}'"
            tipo_check = "RESOLUCION"
        else:
            texto_check = f"{actor_nom} reabrió la falla: '{falla_nom}'"
            tipo_check = "REAPERTURA"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud_id,
            usuario_id=mecanico_id,
            tipo=tipo_check,
            comentario=texto_check,
            fecha_registro=now,
        )
        if u_mec:
            comentario_entry.usuario = u_mec
        self.repo.add_comentario(db, comentario_entry)

        await db.commit()
        # Nivel 3: retornar DTO atómico construido en memoria (0 RTTs adicionales)
        return DetalleUpdateDTO(
            detalle_id=detalle_target.id,
            solicitud_id=solicitud_id,
            resuelto=detalle_target.resuelto,
            falta_repuesto=getattr(detalle_target, "falta_repuesto", False),
            mecanico_resolvio_id=detalle_target.mecanico_resolvio_id,
            mecanico_resolvio_nombre=resolutor_nom if resuelto else None,
            comentario_repuesto=getattr(detalle_target, "comentario_repuesto", None),
            fecha_resolucion=detalle_target.fecha_resolucion,
        )

    async def agregar_comentario(
        self,
        db: AsyncSession,
        solicitud_id: int,
        usuario_id: int,
        dto: ComentarioCreateDTO,
        usuario_nombre: Optional[str] = None,
    ) -> ComentarioAddedDTO:
        logger.info("[MANTENCION] Agregando comentario atómico | solicitud_id=%s | usuario_id=%s | tipo=%s", solicitud_id, usuario_id, dto.tipo)
        if not await self.repo.check_solicitud_exists(db, solicitud_id):
            raise NotFoundException("Solicitud de taller no encontrada")

        if not usuario_nombre:
            u_usr = await self.repo.get_usuario_by_id(db, usuario_id)
        else:
            u_usr = None

        now = datetime.now()
        tipo_com = dto.tipo if dto.tipo else "GENERAL"
        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud_id,
            usuario_id=usuario_id,
            tipo=tipo_com,
            comentario=dto.comentario,
            fecha_registro=now,
        )
        if u_usr:
            comentario_entry.usuario = u_usr
        self.repo.add_comentario(db, comentario_entry)

        await db.commit()
        # Nivel 3: retornar DTO atómico construido en memoria (0 RTTs adicionales)
        # El id del comentario queda disponible tras el commit cuando expire_on_commit=False
        return ComentarioAddedDTO(
            comentario_id=comentario_entry.id,
            solicitud_id=solicitud_id,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre or (u_usr.nombre_completo if u_usr else None),
            tipo=tipo_com,
            comentario=dto.comentario,
            fecha_registro=now,
        )

    async def finalizar_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_cierre_id: int,
        dto: FinalizarSolicitudDTO,
        mecanico_cierre_nom: Optional[str] = None,
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Finalizando solicitud | id=%s | mecanico_cierre_id=%s", solicitud_id, mecanico_cierre_id)
        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        # 1. Validar Checklist / Pauta de Taller Preventiva y obtener datos de mecánico en 1 sola consulta SQL consolidada
        total_items_pauta, items_respondidos, mec_nom_db, _ = await self.repo.get_conteo_pauta_y_mecanico(
            db, solicitud_id, mecanico_cierre_id
        )
        mec_cierre_nom = mecanico_cierre_nom or mec_nom_db or "Mecánico"

        solicitud.motivo_incompleto_checklist = validar_pauta_preventiva_cierre(
            total_items=total_items_pauta,
            items_respondidos=items_respondidos,
            motivo_incompleto=dto.motivo_incompleto_checklist,
        )

        # 2. Validar Cierre Parcial / Fallas no resueltas o falta de repuesto
        fallas_no_resueltas = [
            d for d in (solicitud.detalles or []) if not d.resuelto or getattr(d, "falta_repuesto", False)
        ]
        solicitud.motivo_cierre_parcial = validar_fallas_cierre_parcial(
            cantidad_fallas_no_resueltas=len(fallas_no_resueltas),
            motivo_cierre_parcial=dto.motivo_cierre_parcial,
        )

        if len(fallas_no_resueltas) > 0:
            solicitud.estado = EstadoSolicitud.LIBERADO.value
            solicitud.fecha_cierre = None
            solicitud.fecha_liberacion = now
        else:
            solicitud.estado = EstadoSolicitud.FINALIZADO.value
            solicitud.fecha_cierre = now
            solicitud.fecha_liberacion = None

        solicitud.mecanico_cierre_id = mecanico_cierre_id
        solicitud._mecanico_cierre_nombre_cached = mec_cierre_nom

        # 3. Marcar mecánicos y asignaciones activas como completadas (en bloque sin flushes intermedios)
        await self.repo.desactivar_cuadrilla_y_asignaciones_completas(
            db, solicitud_id=solicitud.id, fecha_desasignacion=now
        )
        if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
            for mec in solicitud.mecanicos:
                if getattr(mec, "is_activo", False):
                    mec.is_activo = False
                    mec.fecha_desasignacion = now
                    if mec.fecha_asignacion:
                        mec.duracion_minutos = calcular_duracion_minutos(mec.fecha_asignacion, now)

        if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas:
            for asig in solicitud.asignaciones_fallas:
                if getattr(asig, "is_activo", False):
                    asig.is_activo = False
                    asig.fecha_desasignacion = now
                    if asig.fecha_asignacion:
                        asig.duracion_minutos = calcular_duracion_minutos(asig.fecha_asignacion, now)

        # 4. Liberar bus del taller si corresponde
        if dto.liberar_bus_taller and solicitud.bus:
            solicitud.bus.en_taller = False
        elif dto.liberar_bus_taller and solicitud.bus_id:
            bus = await self.repo.get_bus_by_id(db, solicitud.bus_id)
            if bus:
                bus.en_taller = False

        # 5. Registrar comentario de cierre en bitácora
        texto_cierre = formatear_comentario_cierre(
            mecanico_nombre=mec_cierre_nom,
            liberar_bus=dto.liberar_bus_taller,
            comentario_cierre=dto.comentario_cierre,
            motivo_cierre_parcial=solicitud.motivo_cierre_parcial,
            motivo_incompleto_checklist=solicitud.motivo_incompleto_checklist,
        )

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_cierre_id,
            tipo=TipoComentarioBitacora.CIERRE.value,
            comentario=texto_cierre,
            fecha_registro=now,
        )
        self.repo.add_comentario(db, comentario_entry)
        self._attach_comentario_safe(solicitud, comentario_entry, mec_cierre_nom)

        await db.commit()
        logger.info(
            "[MANTENCION] Solicitud FINALIZADA | id=%s, bus_id=%s, bus_liberado=%s",
            solicitud.id,
            solicitud.bus_id,
            dto.liberar_bus_taller,
        )
        return self._to_solicitud_dto(solicitud)

    async def autoasignar_fallas(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: AutoasignarFallasDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        logger.info(
            "[MANTENCION] Autoasignando fallas atómicas | solicitud_id=%s, mecanico_id=%s, fallas=%s, colaboradores=%s",
            solicitud_id,
            mecanico_id,
            dto.detalles_ids,
            dto.colaboradores_ids,
        )
        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if not dto.detalles_ids:
            raise BusinessRuleException("Debe seleccionar al menos una falla para autoasignarse")

        sol_detalles_map = {d.id: d for d in solicitud.detalles}
        for d_id in dto.detalles_ids:
            if d_id not in sol_detalles_map:
                raise NotFoundException(f"La falla con ID {d_id} no pertenece a esta solicitud")

        now = datetime.now()
        asignadas_count = 0

        mecanicos_objetivo = [mecanico_id]
        if dto.colaboradores_ids:
            for c_id in dto.colaboradores_ids:
                if c_id not in mecanicos_objetivo:
                    mecanicos_objetivo.append(c_id)

        if not dto.colaboradores_ids and mecanico_nombre:
            users_map = {}
            u_mec = None
            mec_nom = mecanico_nombre
        else:
            from app.modules.auth.repository.user_repository import user_repository
            users_map = await user_repository.get_by_ids_map(db, mecanicos_objetivo)
            u_mec = users_map.get(mecanico_id)
            mec_nom = u_mec.nombre_completo if u_mec else (mecanico_nombre or "Mecánico")

        asigs_activas_todas, presencias_activas_existentes = await asyncio.gather(
            self.repo.get_asignaciones_activas(
                db, solicitud_id=solicitud_id, detalles_ids=dto.detalles_ids
            ),
            self.repo.get_presencias_activas_mecanicos(
                db, solicitud_id=solicitud_id, mecanicos_ids=mecanicos_objetivo
            ),
        )

        for asig in asigs_activas_todas:
            if asig.mecanico_id not in mecanicos_objetivo:
                det_ocupado = sol_detalles_map.get(asig.detalle_id)
                falla_nom = _describir_detalle(det_ocupado) if det_ocupado else f"ID {asig.detalle_id}"
                mec_ocupante = (
                    asig.mecanico.nombre_completo
                    if getattr(asig, "mecanico", None) and getattr(asig.mecanico, "nombre_completo", None)
                    else None
                )
                if not mec_ocupante:
                    u_ocup = await self.repo.get_usuario_by_id(db, asig.mecanico_id)
                    mec_ocupante = u_ocup.nombre_completo if u_ocup else f"Mecánico #{asig.mecanico_id}"
                raise BusinessRuleException(
                    f"La falla '{falla_nom}' ya se encuentra tomada activamente por el mecánico {mec_ocupante}. "
                    f"Debe ser liberada antes de que otro mecánico pueda tomarla."
                )

        activas_existentes = {(a.mecanico_id, a.detalle_id) for a in asigs_activas_todas if a.mecanico_id in mecanicos_objetivo}

        for m_id in mecanicos_objetivo:
            u_target = users_map.get(m_id)
            for d_id in dto.detalles_ids:
                if (m_id, d_id) in activas_existentes:
                    continue

                nueva_asig = TallerAsignacionFalla(
                    solicitud_id=solicitud_id,
                    detalle_id=d_id,
                    mecanico_id=m_id,
                    asignado_por_id=mecanico_id,
                    origen="AUTOASIGNACION",
                    is_activo=True,
                    fecha_asignacion=now,
                    resuelto_en_esta_asignacion=False,
                )
                if u_target:
                    nueva_asig.mecanico = u_target
                if u_mec:
                    nueva_asig.asignado_por = u_mec
                self.repo.add_asignacion_falla(db, nueva_asig)
                if d_id in sol_detalles_map:
                    if not hasattr(sol_detalles_map[d_id], "asignaciones") or sol_detalles_map[d_id].asignaciones is None:
                        sol_detalles_map[d_id].asignaciones = []
                    sol_detalles_map[d_id].asignaciones.append(nueva_asig)
                if not hasattr(solicitud, "asignaciones_fallas") or solicitud.asignaciones_fallas is None:
                    solicitud.asignaciones_fallas = []
                solicitud.asignaciones_fallas.append(nueva_asig)
                asignadas_count += 1

            if m_id not in presencias_activas_existentes:
                nueva_presencia = TallerSolicitudMecanico(
                    solicitud_id=solicitud_id,
                    mecanico_id=m_id,
                    asignado_por_id=mecanico_id,
                    es_lider_responsable=False,
                    is_activo=True,
                    fecha_asignacion=now,
                )
                if u_target:
                    nueva_presencia.mecanico = u_target
                self.repo.add_mecanico(db, nueva_presencia)
                self._attach_mecanico_safe(solicitud, nueva_presencia)
                presencias_activas_existentes.add(m_id)

        if solicitud.estado in [
            EstadoSolicitud.REPORTADO.value,
            EstadoSolicitud.PENDIENTE.value,
            EstadoSolicitud.LIBERADO.value,
        ]:
            if solicitud.estado == EstadoSolicitud.LIBERADO.value:
                solicitud.fecha_liberacion = None
            solicitud.estado = EstadoSolicitud.EN_REPARACION.value
            if solicitud.bus:
                solicitud.bus.en_taller = True
            elif solicitud.bus_id:
                bus = await self.repo.get_bus_by_id(db, solicitud.bus_id)
                if bus:
                    bus.en_taller = True

        colab_nombres = []
        if dto.colaboradores_ids:
            for c_id in dto.colaboradores_ids:
                if c_id != mecanico_id:
                    u_c = users_map.get(c_id)
                    if u_c:
                        colab_nombres.append(u_c.nombre_completo)

        fallas_nombres = [
            _describir_detalle(sol_detalles_map[d_id])
            for d_id in dto.detalles_ids
            if d_id in sol_detalles_map
        ]
        fallas_str = ", ".join(fallas_nombres) if fallas_nombres else "fallas seleccionadas"
        colab_str = f", junto a {', '.join(colab_nombres)}" if colab_nombres else ""

        texto_bitacora = f"{mec_nom} inició trabajo en las fallas: {fallas_str}{colab_str}"
        if dto.comentario and dto.comentario.strip():
            texto_bitacora += f". Nota: {dto.comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="ASIGNACION",
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        if u_mec:
            comentario_entry.usuario = u_mec
        self.repo.add_comentario(db, comentario_entry)
        self._attach_comentario_safe(solicitud, comentario_entry, mec_nom)

        await db.commit()
        logger.info(
            "[MANTENCION] Fallas autoasignadas | solicitud_id=%s, mecanico_id=%s, count=%s",
            solicitud_id,
            mecanico_id,
            asignadas_count,
        )
        return self._to_solicitud_dto(solicitud)

    async def asignar_fallas_supervisora(
        self, db: AsyncSession, solicitud_id: int, dto: AsignarFallasSupervisoraDTO, supervisor_id: int
    ) -> SolicitudDTO:
        logger.info(
            "[MANTENCION] Supervisora asignando fallas | solicitud_id=%s, supervisor_id=%s, mecanico_id=%s, fallas=%s",
            solicitud_id,
            supervisor_id,
            dto.mecanico_id,
            dto.detalles_ids,
        )
        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if not dto.detalles_ids:
            raise BusinessRuleException("Debe indicar al menos una falla para asignar")

        sol_detalles_map = {d.id: d for d in solicitud.detalles}
        for d_id in dto.detalles_ids:
            if d_id not in sol_detalles_map:
                raise NotFoundException(f"La falla con ID {d_id} no pertenece a esta solicitud")

        now = datetime.now()
        asignadas_count = 0

        from app.modules.auth.repository.user_repository import user_repository
        asigs_exist, users_map, presencia = await asyncio.gather(
            self.repo.get_asignaciones_activas(
                db, solicitud_id=solicitud_id, detalles_ids=dto.detalles_ids, mecanicos_ids=[dto.mecanico_id]
            ),
            user_repository.get_by_ids_map(db, [supervisor_id, dto.mecanico_id]),
            self.repo.get_presencia_activa_individual(db, solicitud_id, dto.mecanico_id),
        )
        activas_existentes = {a.detalle_id for a in asigs_exist}

        u_sup = users_map.get(supervisor_id)
        sup_nom = u_sup.nombre_completo if u_sup else "Supervisión"

        u_mec = users_map.get(dto.mecanico_id)
        mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"

        for d_id in dto.detalles_ids:
            if d_id in activas_existentes:
                continue

            nueva_asig = TallerAsignacionFalla(
                solicitud_id=solicitud_id,
                detalle_id=d_id,
                mecanico_id=dto.mecanico_id,
                asignado_por_id=supervisor_id,
                origen="SUPERVISOR",
                is_activo=True,
                fecha_asignacion=now,
                resuelto_en_esta_asignacion=False,
            )
            if u_mec:
                nueva_asig.mecanico = u_mec
            if u_sup:
                nueva_asig.asignado_por = u_sup
            self.repo.add_asignacion_falla(db, nueva_asig)
            if d_id in sol_detalles_map:
                if not hasattr(sol_detalles_map[d_id], "asignaciones") or sol_detalles_map[d_id].asignaciones is None:
                    sol_detalles_map[d_id].asignaciones = []
                sol_detalles_map[d_id].asignaciones.append(nueva_asig)
            if not hasattr(solicitud, "asignaciones_fallas") or solicitud.asignaciones_fallas is None:
                solicitud.asignaciones_fallas = []
            solicitud.asignaciones_fallas.append(nueva_asig)
            asignadas_count += 1

        if not presencia:
            nueva_presencia = TallerSolicitudMecanico(
                solicitud_id=solicitud_id,
                mecanico_id=dto.mecanico_id,
                asignado_por_id=supervisor_id,
                es_lider_responsable=False,
                is_activo=True,
                fecha_asignacion=now,
            )
            if u_mec:
                nueva_presencia.mecanico = u_mec
            self.repo.add_mecanico(db, nueva_presencia)
            self._attach_mecanico_safe(solicitud, nueva_presencia)

        if solicitud.estado in [
            EstadoSolicitud.REPORTADO.value,
            EstadoSolicitud.PENDIENTE.value,
            EstadoSolicitud.LIBERADO.value,
        ]:
            if solicitud.estado == EstadoSolicitud.LIBERADO.value:
                solicitud.fecha_liberacion = None
            solicitud.estado = EstadoSolicitud.EN_REPARACION.value
            if solicitud.bus:
                solicitud.bus.en_taller = True
            elif solicitud.bus_id:
                bus = await self.repo.get_bus_by_id(db, solicitud.bus_id)
                if bus:
                    bus.en_taller = True

        fallas_nombres = [
            _describir_detalle(sol_detalles_map[d_id])
            for d_id in dto.detalles_ids
            if d_id in sol_detalles_map
        ]
        fallas_str = ", ".join(fallas_nombres) if fallas_nombres else "fallas indicadas"

        texto_bitacora = f"{sup_nom} asignó las fallas [{fallas_str}] al mecánico {mec_nom}"
        if dto.comentario and dto.comentario.strip():
            texto_bitacora += f". Nota: {dto.comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=supervisor_id,
            tipo="ASIGNACION",
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        if u_sup:
            comentario_entry.usuario = u_sup
        self.repo.add_comentario(db, comentario_entry)
        self._attach_comentario_safe(solicitud, comentario_entry, sup_nom)

        await db.commit()
        logger.info(
            "[MANTENCION] Supervisora asignó fallas | solicitud_id=%s, supervisor_id=%s, mecanico_id=%s, count=%s",
            solicitud_id,
            supervisor_id,
            dto.mecanico_id,
            asignadas_count,
        )
        return self._to_solicitud_dto(solicitud)

    async def cambiar_estado_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: CambiarEstadoSolicitudDTO,
        supervisor_id: int,
        supervisor_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        """
        Cambia el estado de una OT por parte de la supervisora o administradores.
        Registra un comentario explicativo en la bitácora inmutable (tipo CAMBIO_ESTADO)
        con marcas de tiempo y gestiona el bus y la cuadrilla de forma segura.
        """
        logger.info(
            "[MANTENCION] Cambio de estado de OT solicitado por supervisora | solicitud_id=%s, nuevo_estado=%s, supervisor_id=%s",
            solicitud_id,
            dto.estado.value,
            supervisor_id,
        )
        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        nuevo_estado = dto.estado.value
        estado_anterior = solicitud.estado
        if estado_anterior == nuevo_estado:
            raise BusinessRuleException(
                f"La solicitud ya se encuentra en estado '{nuevo_estado}'"
            )

        now = datetime.now()
        sup_nom = supervisor_nombre

        if not sup_nom:
            u_sup = await self.repo.get_usuario_by_id(db, supervisor_id)
            sup_nom = u_sup.nombre_completo if u_sup else "Supervisora"
        else:
            u_sup = None

        # 1. Transición hacia FINALIZADO
        if nuevo_estado == EstadoSolicitud.FINALIZADO.value:
            solicitud.fecha_cierre = now
            solicitud.fecha_liberacion = None
            solicitud.mecanico_cierre_id = supervisor_id
            solicitud._mecanico_cierre_nombre_cached = sup_nom

            await self.repo.desactivar_cuadrilla_y_asignaciones_completas(
                db, solicitud_id=solicitud.id, fecha_desasignacion=now
            )
            if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
                for mec in solicitud.mecanicos:
                    if getattr(mec, "is_activo", False):
                        mec.is_activo = False
                        mec.fecha_desasignacion = now
                        if mec.fecha_asignacion:
                            mec.duracion_minutos = calcular_duracion_minutos(mec.fecha_asignacion, now)

            if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas:
                for asig in solicitud.asignaciones_fallas:
                    if getattr(asig, "is_activo", False):
                        asig.is_activo = False
                        asig.fecha_desasignacion = now
                        if asig.fecha_asignacion:
                            asig.duracion_minutos = calcular_duracion_minutos(asig.fecha_asignacion, now)

            debe_liberar = True if dto.liberar_bus_taller is None else dto.liberar_bus_taller
            if debe_liberar:
                if solicitud.bus:
                    solicitud.bus.en_taller = False
                elif solicitud.bus_id:
                    bus = await self.repo.get_bus_by_id(db, solicitud.bus_id)
                    if bus:
                        bus.en_taller = False

        # 2. Transición hacia LIBERADO (cierre parcial / egreso con fallas o repuestos pendientes)
        elif nuevo_estado == EstadoSolicitud.LIBERADO.value:
            solicitud.fecha_cierre = None
            solicitud.fecha_liberacion = now
            await self.repo.desactivar_cuadrilla_y_asignaciones_completas(
                db, solicitud_id=solicitud.id, fecha_desasignacion=now
            )
            if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
                for mec in solicitud.mecanicos:
                    if getattr(mec, "is_activo", False):
                        mec.is_activo = False
                        mec.fecha_desasignacion = now
                        if mec.fecha_asignacion:
                            mec.duracion_minutos = calcular_duracion_minutos(mec.fecha_asignacion, now)

            if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas:
                for asig in solicitud.asignaciones_fallas:
                    if getattr(asig, "is_activo", False):
                        asig.is_activo = False
                        asig.fecha_desasignacion = now
                        if asig.fecha_asignacion:
                            asig.duracion_minutos = calcular_duracion_minutos(asig.fecha_asignacion, now)

            debe_liberar = True if dto.liberar_bus_taller is None else dto.liberar_bus_taller
            if debe_liberar:
                if solicitud.bus:
                    solicitud.bus.en_taller = False
                elif solicitud.bus_id:
                    bus = await self.repo.get_bus_by_id(db, solicitud.bus_id)
                    if bus:
                        bus.en_taller = False

        # 3. Reapertura desde FINALIZADO o LIBERADO a estado activo
        elif estado_anterior in (EstadoSolicitud.FINALIZADO.value, EstadoSolicitud.LIBERADO.value) and nuevo_estado not in (EstadoSolicitud.FINALIZADO.value, EstadoSolicitud.LIBERADO.value):
            solicitud.fecha_cierre = None
            solicitud.fecha_liberacion = None
            solicitud.mecanico_cierre_id = None
            solicitud._mecanico_cierre_nombre_cached = None
            if nuevo_estado == EstadoSolicitud.EN_REPARACION.value:
                if solicitud.bus:
                    solicitud.bus.en_taller = True
                elif solicitud.bus_id:
                    bus = await self.repo.get_bus_by_id(db, solicitud.bus_id)
                    if bus:
                        bus.en_taller = True

        # 4. Transición a PENDIENTE o REPORTADO
        elif nuevo_estado in (
            EstadoSolicitud.PENDIENTE.value,
            EstadoSolicitud.REPORTADO.value,
        ):
            await self.repo.desactivar_cuadrilla_y_asignaciones_completas(
                db, solicitud_id=solicitud.id, fecha_desasignacion=now
            )
            if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
                for mec in solicitud.mecanicos:
                    if getattr(mec, "is_activo", False):
                        mec.is_activo = False
                        mec.fecha_desasignacion = now
                        if mec.fecha_asignacion:
                            mec.duracion_minutos = calcular_duracion_minutos(mec.fecha_asignacion, now)

        # 5. Transición a EN_REPARACION asegurando que el bus figure en taller
        elif nuevo_estado == EstadoSolicitud.EN_REPARACION.value:
            if solicitud.bus:
                solicitud.bus.en_taller = True
            elif solicitud.bus_id:
                bus = await self.repo.get_bus_by_id(db, solicitud.bus_id)
                if bus:
                    bus.en_taller = True

        # 5. Aplicar nuevo estado
        solicitud.estado = nuevo_estado

        # 6. Registrar comentario inmutable de tipo CAMBIO_ESTADO
        base_texto = f"Supervisora {sup_nom} cambió el estado de {estado_anterior} a {nuevo_estado}"
        if dto.comentario and dto.comentario.strip():
            texto_bitacora = f"{base_texto}. Motivo: {dto.comentario.strip()}"
        else:
            texto_bitacora = f"{base_texto}."

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=supervisor_id,
            tipo=TipoComentarioBitacora.CAMBIO_ESTADO.value,
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        if u_sup:
            comentario_entry.usuario = u_sup
        self.repo.add_comentario(db, comentario_entry)
        self._attach_comentario_safe(solicitud, comentario_entry, sup_nom)

        await db.commit()
        logger.info(
            "[MANTENCION] Estado de OT actualizado por supervisora | solicitud_id=%s, estado_anterior=%s, nuevo_estado=%s",
            solicitud_id,
            estado_anterior,
            nuevo_estado,
        )
        return self._to_solicitud_dto(solicitud)

    async def terminar_avance(

        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: TerminarAvanceDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        logger.info(
            "[MANTENCION] Registrando término de avance | solicitud_id=%s, mecanico_id=%s, fallas=%s",
            solicitud_id,
            mecanico_id,
            dto.detalles_ids,
        )
        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        # Nivel 2: paralelizar SELECTs independientes en 1 solo RTT con asyncio.gather
        todas_asigs_activas, presencias_activas = await asyncio.gather(
            self.repo.get_asignaciones_activas(db, solicitud_id=solicitud_id),
            self.repo.get_presencias_activas(db, solicitud_id=solicitud_id),
        )

        mi_presencia = next((p for p in presencias_activas if p.mecanico_id == mecanico_id and p.is_activo), None)
        mis_asigs_activas = [a for a in todas_asigs_activas if a.mecanico_id == mecanico_id]

        if not mis_asigs_activas and not mi_presencia:
            raise BusinessRuleException("El mecánico no tiene asignaciones ni presencia activa para finalizar avance en esta solicitud")

        sol_detalles_map = {d.id: d for d in solicitud.detalles}

        # Determinar qué fallas se van a cerrar:
        if dto.detalles_ids:
            target_detalles_ids = set(dto.detalles_ids)
        else:
            target_detalles_ids = {a.detalle_id for a in mis_asigs_activas}

        # Asignaciones a cerrar: solo las de target_detalles_ids donde participa este mecánico (incluyendo su equipo en esas fallas)
        mis_fallas_ids = {a.detalle_id for a in mis_asigs_activas}
        asignaciones_activas = [
            a for a in todas_asigs_activas
            if a.detalle_id in target_detalles_ids
            and (a.mecanico_id == mecanico_id or a.detalle_id in mis_fallas_ids)
        ]

        mecanicos_involucrados_ids = {a.mecanico_id for a in asignaciones_activas}
        if mi_presencia:
            mecanicos_involucrados_ids.add(mecanico_id)

        cerradas_asig_ids = set()

        for asig in asignaciones_activas:
            asig.is_activo = False
            asig.fecha_desasignacion = now
            if asig.fecha_asignacion:
                asig.duracion_minutos = _calcular_duracion_minutos(asig.fecha_asignacion, now)
            det = sol_detalles_map.get(asig.detalle_id)
            asig.resuelto_en_esta_asignacion = bool(det and det.resuelto)
            if dto.comentario and dto.comentario.strip():
                asig.comentario = dto.comentario.strip()
            cerradas_asig_ids.add(asig.id)

        con_restantes_ids = set()
        if cerradas_asig_ids:
            con_restantes_ids = await self.repo.get_asignaciones_activas_restantes(
                db, solicitud_id, mecanicos_involucrados_ids, cerradas_asig_ids
            )

        presencias_cerradas_ids = set()
        for p in presencias_activas:
            if p.mecanico_id in mecanicos_involucrados_ids and p.mecanico_id not in con_restantes_ids:
                p.is_activo = False
                p.fecha_desasignacion = now
                if p.fecha_asignacion:
                    p.duracion_minutos = _calcular_duracion_minutos(p.fecha_asignacion, now)
                presencias_cerradas_ids.add(p.id)

        quedan_presencias = any(p.is_activo for p in presencias_activas if p.id not in presencias_cerradas_ids)

        if cerradas_asig_ids:
            quedan_asignaciones = await self.repo.get_otras_asignaciones_activas(
                db, solicitud_id, cerradas_asig_ids
            )
        else:
            quedan_asignaciones = False

        if not quedan_presencias and not quedan_asignaciones:
            solicitud.estado = EstadoSolicitud.PENDIENTE.value
            logger.info("[MANTENCION] Solicitud sin cuadrilla activa → PENDIENTE | solicitud_id=%s", solicitud_id)

        if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas:
            for asig in solicitud.asignaciones_fallas:
                if asig.id in cerradas_asig_ids:
                    asig.is_activo = False
                    asig.fecha_desasignacion = now
                    if asig.fecha_asignacion:
                        asig.duracion_minutos = _calcular_duracion_minutos(asig.fecha_asignacion, now)

        if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
            for mec in solicitud.mecanicos:
                if mec.id in presencias_cerradas_ids:
                    mec.is_activo = False
                    mec.fecha_desasignacion = now
                    if mec.fecha_asignacion:
                        mec.duracion_minutos = _calcular_duracion_minutos(mec.fecha_asignacion, now)

        mecanicos_nombres = []
        u_ejecutor = None
        if mecanico_nombre and (not mecanicos_involucrados_ids or mecanicos_involucrados_ids == {mecanico_id}):
            ejecutor_nombre = mecanico_nombre
            mecanicos_nombres = [mecanico_nombre]
        else:
            from app.modules.auth.repository.user_repository import user_repository
            all_ids = list(mecanicos_involucrados_ids)
            if mecanico_id not in all_ids:
                all_ids.append(mecanico_id)
            users_map = await user_repository.get_by_ids_map(db, all_ids)

            for m_id in sorted(mecanicos_involucrados_ids):
                u = users_map.get(m_id)
                mecanicos_nombres.append(u.nombre_completo if u else "Mecánico")

            u_ejecutor = users_map.get(mecanico_id)
            ejecutor_nombre = u_ejecutor.nombre_completo if u_ejecutor else (mecanico_nombre or "Mecánico")

        fallas_involucradas = [
            _describir_detalle(sol_detalles_map[a.detalle_id])
            for a in asignaciones_activas
            if a.detalle_id in sol_detalles_map
        ]
        fallas_unicas = list(dict.fromkeys(fallas_involucradas))
        fallas_str = ", ".join(fallas_unicas)

        if len(mecanicos_involucrados_ids) > 1:
            texto_bitacora = f"{ejecutor_nombre} finalizó avance grupal para el equipo [{', '.join(mecanicos_nombres)}]"
        else:
            texto_bitacora = f"{ejecutor_nombre} finalizó avance de trabajo"

        if fallas_str:
            texto_bitacora += f" en las fallas: {fallas_str}"

        if dto.comentario and dto.comentario.strip():
            texto_bitacora += f": {dto.comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="ENTREGA_TURNO",
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        if u_ejecutor:
            comentario_entry.usuario = u_ejecutor
        self.repo.add_comentario(db, comentario_entry)
        self._attach_comentario_safe(solicitud, comentario_entry, ejecutor_nombre)

        await db.commit()
        logger.info(
            "[MANTENCION] Avance finalizado (grupal/individual) | solicitud_id=%s, ejecutado_por=%s, involucrados=%s, estado_final=%s",
            solicitud_id,
            mecanico_id,
            list(mecanicos_involucrados_ids),
            solicitud.estado,
        )
        return self._to_solicitud_dto(solicitud)

    async def reportar_repuesto(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        dto: ReportarRepuestoDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> DetalleUpdateDTO:
        logger.info(
            "[MANTENCION] Reportando repuesto atómico | solicitud_id=%s, detalle_id=%s, falta=%s",
            solicitud_id,
            detalle_id,
            dto.falta_repuesto,
        )
        detalle = await self.repo.get_detalle_operacional(db, solicitud_id, detalle_id)
        if not detalle:
            if not await self.repo.check_solicitud_exists(db, solicitud_id):
                raise NotFoundException("Solicitud de taller no encontrada")
            raise NotFoundException(f"Detalle con ID {detalle_id} no encontrado en la solicitud")

        if dto.falta_repuesto and getattr(detalle, "resuelto", False):
            raise BusinessRuleException(
                "No se puede reportar falta de repuesto en una falla que ya fue marcada como resuelta. "
                "Si la falla requiere nueva intervención, desmarque primero su resolución."
            )

        detalle.falta_repuesto = dto.falta_repuesto
        detalle.comentario_repuesto = dto.comentario.strip() if dto.comentario else None

        now = datetime.now()
        tipo_accion = "FALTA_REPUESTO" if dto.falta_repuesto else "REPUESTO_DISPONIBLE"

        if not mecanico_nombre:
            u_mec = await self.repo.get_usuario_by_id(db, mecanico_id)
            mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"
        else:
            u_mec = None
            mec_nom = mecanico_nombre

        falla_nom = _describir_detalle(detalle)
        estado_str = "FALTA DE REPUESTO" if dto.falta_repuesto else "REPUESTO DISPONIBLE"

        texto = f"{mec_nom} reportó {estado_str} para la falla: '{falla_nom}'"
        if dto.comentario and dto.comentario.strip():
            texto += f" - Detalle: {dto.comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud_id,
            usuario_id=mecanico_id,
            tipo=tipo_accion,
            comentario=texto,
            fecha_registro=now,
        )
        if u_mec:
            comentario_entry.usuario = u_mec
        self.repo.add_comentario(db, comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Reporte de repuesto guardado | solicitud_id=%s, detalle_id=%s, falta_repuesto=%s",
            solicitud_id,
            detalle_id,
            dto.falta_repuesto,
        )
        # Nivel 3: retornar DTO atómico construido en memoria (0 RTTs adicionales)
        return DetalleUpdateDTO(
            detalle_id=detalle.id,
            solicitud_id=solicitud_id,
            resuelto=getattr(detalle, "resuelto", False),
            falta_repuesto=detalle.falta_repuesto,
            mecanico_resolvio_id=getattr(detalle, "mecanico_resolvio_id", None),
            mecanico_resolvio_nombre=None,
            comentario_repuesto=detalle.comentario_repuesto,
            fecha_resolucion=getattr(detalle, "fecha_resolucion", None),
        )

    async def get_pauta_items(self, db: AsyncSession) -> List[PautaTallerItemDTO]:
        items = await self.repo.get_pauta_items(db)
        return [PautaTallerItemDTO.model_validate(it) for it in items]

    async def get_pauta_resumen(
        self, db: AsyncSession, solicitud_id: int
    ) -> PautaEstadoResumenDTO:
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
        logger.info(
            "[PAUTA] Guardando respuestas de pauta | solicitud_id=%s, total_respuestas=%s",
            solicitud_id,
            len(dto.respuestas),
        )
        if not dto.respuestas:
            raise BusinessRuleException("Debe enviar al menos una respuesta de pauta")

        now = datetime.now()

        # 1. Validar existencia de solicitud, obtener datos del mecánico y verificar ítems en paralelo
        item_ids = [r.item_id for r in dto.respuestas]
        valid_item_ids, (total_p, resp_p, mec_nom, sol_existe) = await asyncio.gather(
            self.repo.get_pauta_items_by_ids(db, item_ids),
            self.repo.get_conteo_pauta_y_mecanico(db, solicitud_id, mecanico_id),
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
        self.repo.add_comentario(db, comentario_entry)

        await db.commit()
        return await self.get_pauta_resumen(db, solicitud_id)

    async def liberar_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: LiberarSolicitudDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        logger.info(
            "[MANTENCION] Liberación de solicitud solicitada | solicitud_id=%s, mecanico_id=%s, liberar_bus=%s",
            solicitud_id,
            mecanico_id,
            dto.liberar_bus_taller,
        )
        return await self.finalizar_solicitud(
            db=db,
            solicitud_id=solicitud_id,
            mecanico_cierre_id=mecanico_id,
            dto=dto,
            mecanico_cierre_nom=mecanico_nombre,
        )

    async def agregar_falla(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        dto: AgregarFallaDTO,
    ) -> SolicitudDTO:
        logger.info(
            "[MANTENCION] Agregando nueva avería | solicitud_id=%s, mecanico_id=%s, autoasignar=%s",
            solicitud_id,
            mecanico_id,
            dto.autoasignar,
        )
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if solicitud.estado == "FINALIZADO":
            raise BusinessRuleException("No se pueden agregar fallas a una solicitud que ya ha sido finalizada")

        now = datetime.now()
        falla_id = dto.falla_id

        # 1. Resolver falla_id y objeto f_obj si corresponde
        cat_obj = None
        f_obj = None
        if not falla_id and dto.categoria_id:
            cat_obj = await self.repo.get_categoria_by_id(db, dto.categoria_id)
            falla_id = await self.repo.find_falla_activa_by_categoria(db, dto.categoria_id)
            if not falla_id:
                cat_nom = cat_obj.nombre if cat_obj else f"Categoría #{dto.categoria_id}"
                f_obj = FallaTaller(
                    categoria_id=dto.categoria_id,
                    nombre=f"Avería de {cat_nom}",
                    is_active=True,
                )
                if cat_obj:
                    f_obj.categoria = cat_obj
                self.repo.add_falla(db, f_obj)
                await self.repo.flush(db)
                falla_id = f_obj.id
            else:
                f_obj = await self.repo.get_falla_by_id(db, falla_id)
        elif falla_id:
            f_obj = await self.repo.get_falla_by_id(db, falla_id)
        else:
            if not dto.descripcion_personalizada or not dto.descripcion_personalizada.strip():
                raise BusinessRuleException("Debe indicar al menos una categoría, falla o descripción personalizada de la avería")
            falla_id = await self.repo.find_falla_otro(db)
            if falla_id:
                f_obj = await self.repo.get_falla_by_id(db, falla_id)

        # 2. Registrar mecánico ejecutor
        u = await self.repo.get_usuario_by_id(db, mecanico_id)
        mec_nombre = u.nombre_completo if u else "Mecánico"

        # 3. Crear nuevo detalle de falla con colección asignaciones pre-inicializada
        nuevo_detalle = TallerSolicitudDetalle(
            solicitud_id=solicitud.id,
            falla_id=falla_id,
            descripcion_personalizada=dto.descripcion_personalizada.strip() if dto.descripcion_personalizada else None,
            resuelto=False,
            falta_repuesto=False,
            fecha_creacion=now,
            asignaciones=[],
        )
        if f_obj:
            nuevo_detalle.falla = f_obj
        self.repo.add_detalle(db, nuevo_detalle)
        await self.repo.flush(db)

        # 4. Asignación / Resolución según rol y DTO
        es_supervisor = False
        u_rol_nom = getattr(getattr(u, "rol_rel", None), "nombre", None) or ""
        if u and u_rol_nom.upper().strip() in [RolUsuario.SUPERVISOR.value, RolUsuario.ADMIN.value]:
            es_supervisor = True

        tipo_bitacora = "AVANCE"
        u_resolutor = None
        u_asig = None

        resolutor_id = dto.effective_resolutor_id
        asignado_id = dto.effective_asignado_id

        if es_supervisor and dto.resuelto and resolutor_id:
            u_resolutor = await self.repo.get_usuario_by_id(db, resolutor_id)
            if not u_resolutor or not u_resolutor.is_active:
                raise BusinessRuleException("El mecánico resolutor indicado no existe o se encuentra inactivo")
            nuevo_detalle.resuelto = True
            nuevo_detalle.mecanico_resolvio_id = resolutor_id
            nuevo_detalle.mecanico_resolvio = u_resolutor
            nuevo_detalle.fecha_resolucion = now
            db.add(nuevo_detalle)
            tipo_bitacora = "RESOLUCION"
        elif es_supervisor and asignado_id:
            u_asig = await self.repo.get_usuario_by_id(db, asignado_id)
            if not u_asig or not u_asig.is_active:
                raise BusinessRuleException("El mecánico asignado indicado no existe o se encuentra inactivo")
            nueva_asig = TallerAsignacionFalla(
                solicitud_id=solicitud.id,
                detalle_id=nuevo_detalle.id,
                mecanico_id=asignado_id,
                asignado_por_id=mecanico_id,
                origen="SUPERVISION",
                is_activo=True,
                fecha_asignacion=now,
                resuelto_en_esta_asignacion=False,
            )
            nueva_asig.mecanico = u_asig
            nueva_asig.asignado_por = u
            self.repo.add_asignacion_falla(db, nueva_asig)
            nuevo_detalle.asignaciones.append(nueva_asig)
            if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas is not None:
                solicitud.asignaciones_fallas.append(nueva_asig)

            presencia = await self.repo.get_presencia_activa_individual(db, solicitud.id, dto.mecanico_asignado_id)
            if not presencia:
                nueva_presencia = TallerSolicitudMecanico(
                    solicitud_id=solicitud.id,
                    mecanico_id=dto.mecanico_asignado_id,
                    asignado_por_id=mecanico_id,
                    es_lider_responsable=False,
                    is_activo=True,
                    fecha_asignacion=now,
                )
                nueva_presencia.mecanico = u_asig
                self.repo.add_mecanico(db, nueva_presencia)
                self._attach_mecanico_safe(solicitud, nueva_presencia)

            if solicitud.estado in [
                EstadoSolicitud.REPORTADO.value,
                EstadoSolicitud.PENDIENTE.value,
                EstadoSolicitud.LIBERADO.value,
            ]:
                solicitud.estado = EstadoSolicitud.EN_REPARACION.value
                if solicitud.bus:
                    solicitud.bus.en_taller = True
                elif solicitud.bus_id:
                    bus = await self.repo.get_bus_by_id(db, solicitud.bus_id)
                    if bus:
                        bus.en_taller = True
        else:
            debe_autoasignar = dto.autoasignar and not es_supervisor
            if debe_autoasignar:
                nueva_asig = TallerAsignacionFalla(
                    solicitud_id=solicitud.id,
                    detalle_id=nuevo_detalle.id,
                    mecanico_id=mecanico_id,
                    asignado_por_id=mecanico_id,
                    origen="AUTOASIGNACION",
                    is_activo=True,
                    fecha_asignacion=now,
                    resuelto_en_esta_asignacion=False,
                )
                if u:
                    nueva_asig.mecanico = u
                    nueva_asig.asignado_por = u
                self.repo.add_asignacion_falla(db, nueva_asig)
                nuevo_detalle.asignaciones.append(nueva_asig)
                if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas is not None:
                    solicitud.asignaciones_fallas.append(nueva_asig)

                presencia = await self.repo.get_presencia_activa_individual(db, solicitud.id, mecanico_id)
                if not presencia:
                    nueva_presencia = TallerSolicitudMecanico(
                        solicitud_id=solicitud.id,
                        mecanico_id=mecanico_id,
                        asignado_por_id=mecanico_id,
                        es_lider_responsable=False,
                        is_activo=True,
                        fecha_asignacion=now,
                    )
                    if u:
                        nueva_presencia.mecanico = u
                    self.repo.add_mecanico(db, nueva_presencia)
                    self._attach_mecanico_safe(solicitud, nueva_presencia)

                if solicitud.estado in [
                    EstadoSolicitud.REPORTADO.value,
                    EstadoSolicitud.PENDIENTE.value,
                    EstadoSolicitud.LIBERADO.value,
                ]:
                    solicitud.estado = EstadoSolicitud.EN_REPARACION.value
                    if solicitud.bus:
                        solicitud.bus.en_taller = True
                    elif solicitud.bus_id:
                        bus = await self.repo.get_bus_by_id(db, solicitud.bus_id)
                        if bus:
                            bus.en_taller = True

        if hasattr(solicitud, "detalles") and solicitud.detalles is not None:
            solicitud.detalles.append(nuevo_detalle)

        # 5. Registrar en bitácora inmutable
        desc_pers = dto.descripcion_personalizada.strip() if dto.descripcion_personalizada else None
        nom_falla_o_cat = None
        if f_obj:
            nom_falla_o_cat = f_obj.nombre
        elif cat_obj:
            nom_falla_o_cat = f"Avería de {cat_obj.nombre}"

        if nom_falla_o_cat and desc_pers:
            falla_txt = f"{nom_falla_o_cat} ({desc_pers})"
        elif nom_falla_o_cat:
            falla_txt = nom_falla_o_cat
        elif desc_pers:
            falla_txt = desc_pers
        else:
            falla_txt = "Avería general"

        if es_supervisor:
            if u_resolutor:
                texto_bitacora = f"Supervisora {mec_nombre} agregó la avería '{falla_txt}' resuelta por el mecánico {u_resolutor.nombre_completo}"
            elif u_asig:
                texto_bitacora = f"Supervisora {mec_nombre} agregó una nueva avería: '{falla_txt}' (asignada a {u_asig.nombre_completo})"
            else:
                texto_bitacora = f"Supervisora {mec_nombre} agregó una nueva avería a la orden: '{falla_txt}'"
        else:
            texto_bitacora = f"{mec_nombre} detectó y agregó una nueva avería a la orden: '{falla_txt}'"
            if dto.autoasignar:
                texto_bitacora += f" (autoasignada a {mec_nombre})"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo=tipo_bitacora,
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        if u:
            comentario_entry.usuario = u
        self.repo.add_comentario(db, comentario_entry)
        self._attach_comentario_safe(solicitud, comentario_entry, mec_nombre)

        await db.commit()
        logger.info(
            "[MANTENCION] Nueva avería agregada a solicitud #%s por usuario #%s | detalle_id=%s, es_supervisor=%s",
            solicitud_id,
            mecanico_id,
            nuevo_detalle.id,
            es_supervisor,
        )
        return self._to_solicitud_dto(solicitud)

    async def resolver_falla_supervisora(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        dto: ResolverFallaSupervisoraDTO,
        supervisor_id: int,
        supervisor_nombre: Optional[str] = None,
    ) -> DetalleUpdateDTO:
        """
        Permite a la supervisora marcar una falla como resuelta indicando qué mecánico
        la arregló, o reabrirla si requiere revisión posterior, dejando constancia en la bitácora inmutable.
        """
        logger.info(
            "[MANTENCION] Supervisora gestionando resolución de falla | solicitud_id=%s | detalle_id=%s | supervisor_id=%s | resuelto=%s | mecanico_id=%s",
            solicitud_id,
            detalle_id,
            supervisor_id,
            dto.resuelto,
            dto.mecanico_id,
        )
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if solicitud.estado == EstadoSolicitud.FINALIZADO.value:
            raise BusinessRuleException("No se pueden modificar fallas de una solicitud que ya ha sido finalizada")

        detalle_target = None
        if hasattr(solicitud, "detalles") and solicitud.detalles:
            for det in solicitud.detalles:
                if det.id == detalle_id:
                    detalle_target = det
                    break

        if not detalle_target:
            detalle_target = await self.repo.get_detalle_operacional(db, solicitud_id, detalle_id)

        if not detalle_target:
            raise NotFoundException("Detalle de falla no encontrado en la orden de taller")

        now = datetime.now()
        falla_nom = _describir_detalle(detalle_target)

        sup_nom = supervisor_nombre
        if not sup_nom:
            u_sup = await self.repo.get_usuario_by_id(db, supervisor_id)
            sup_nom = u_sup.nombre_completo if u_sup else "Supervisora"

        mec_nom = None
        u_mec = None

        mec_id = dto.effective_mecanico_id

        if dto.resuelto:
            if not mec_id:
                raise BusinessRuleException("Debe indicar el ID del mecánico que realizó la reparación de la avería")

            if getattr(detalle_target, "falta_repuesto", False):
                raise BusinessRuleException(
                    "No se puede marcar como resuelta una falla que se encuentra a la espera de repuesto. "
                    "Debe registrarse primero la recepción/disponibilidad del repuesto."
                )

            u_mec = await self.repo.get_usuario_by_id(db, mec_id)
            if not u_mec or not u_mec.is_active:
                raise BusinessRuleException("El mecánico indicado no existe o no se encuentra activo en el sistema")

            mec_nom = u_mec.nombre_completo
            detalle_target.resuelto = True
            detalle_target.mecanico_resolvio_id = mec_id
            detalle_target.mecanico_resolvio = u_mec
            detalle_target.fecha_resolucion = now
            db.add(detalle_target)

            # Si el mecánico tenía asignación activa en esta falla, marcarla como resuelta
            if hasattr(detalle_target, "asignaciones") and detalle_target.asignaciones:
                for asig in detalle_target.asignaciones:
                    if asig.mecanico_id == mec_id and asig.is_activo:
                        asig.resuelto_en_esta_asignacion = True

            texto_check = f"Supervisora {sup_nom} registró la reparación de la falla '{falla_nom}' por el mecánico {mec_nom}"
            if dto.comentario and dto.comentario.strip():
                texto_check += f" - Observación: {dto.comentario.strip()}"
            tipo_check = "RESOLUCION"
        else:
            detalle_target.resuelto = False
            detalle_target.mecanico_resolvio_id = None
            detalle_target.mecanico_resolvio = None
            detalle_target.fecha_resolucion = None
            db.add(detalle_target)

            texto_check = f"Supervisora {sup_nom} reabrió la falla '{falla_nom}'"
            if dto.comentario and dto.comentario.strip():
                texto_check += f" - Observación: {dto.comentario.strip()}"
            tipo_check = "REAPERTURA"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud_id,
            usuario_id=supervisor_id,
            tipo=tipo_check,
            comentario=texto_check,
            fecha_registro=now,
        )
        self.repo.add_comentario(db, comentario_entry)

        await db.commit()

        return DetalleUpdateDTO(
            detalle_id=detalle_target.id,
            solicitud_id=solicitud_id,
            resuelto=detalle_target.resuelto,
            falta_repuesto=getattr(detalle_target, "falta_repuesto", False),
            mecanico_resolvio_id=detalle_target.mecanico_resolvio_id,
            mecanico_resolvio_nombre=mec_nom if dto.resuelto else None,
            comentario_repuesto=getattr(detalle_target, "comentario_repuesto", None),
            fecha_resolucion=detalle_target.fecha_resolucion,
        )


mantencion_service = MantencionService()
