import json
from typing import Any, List, Optional
from app.core.storage.storage_service import storage_service, StorageService
from app.modules.taller.constants import TOTAL_ITEMS_PAUTA_PREVENTIVA
from app.modules.taller.dtos import (
    AsignacionFallaDTO,
    CategoriaFallaDTO,
    EstadiaTallerDTO,
    FallaTallerDTO,
    MecanicoAsignadoDTO,
    MecanicoResumenDTO,
    PautaRespuestaDTO,
    SolicitudComentarioDTO,
    SolicitudDetalleDTO,
    SolicitudDTO,
    SolicitudEvidenciaDTO,
    SolicitudMecanicoDTO,
    SolicitudResumenDTO,
)
from app.modules.taller.utils import (
    calcular_horas_en_taller,
    calcular_telemetria_estadias,
)


def parse_evidencias_dtos(
    evidencias_raw: Any, storage: StorageService = storage_service
) -> List[SolicitudEvidenciaDTO]:
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
        signed_url = storage.get_url(raw_url) or raw_url
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


def dict_to_solicitud_dto(
    r: dict, storage: StorageService = storage_service
) -> SolicitudDTO:
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
    evidencias_dtos = parse_evidencias_dtos(r.get("evidencias_json"), storage=storage)

    tot = (
        r["total_fallas"]
        if "total_fallas" in r and r["total_fallas"] is not None
        else len(detalles_raw)
    )
    resueltos = (
        r["fallas_resueltas"]
        if "fallas_resueltas" in r and r["fallas_resueltas"] is not None
        else sum(
            1 for d in detalles_raw if d.get("estado") == "RESUELTA" or (d.get("estado") is None and d.get("resuelto"))
        )
    )
    incompletas = (
        r["fallas_incompletas"]
        if "fallas_incompletas" in r and r["fallas_incompletas"] is not None
        else sum(1 for d in detalles_raw if d.get("estado") == "INCOMPLETA")
    )
    faltas = (
        r["fallas_con_falta_repuesto"]
        if "fallas_con_falta_repuesto" in r and r["fallas_con_falta_repuesto"] is not None
        else sum(1 for d in detalles_raw if d.get("falta_repuesto"))
    )
    pendientes = (
        r["fallas_pendientes"]
        if "fallas_pendientes" in r and r["fallas_pendientes"] is not None
        else (tot - resueltos - incompletas)
    )
    pauta_completada = len(pauta_respuestas_raw) >= TOTAL_ITEMS_PAUTA_PREVENTIVA

    if r.get("estado") == "FINALIZADO" and not mecanicos_raw and historial_mecanicos_raw:
        vistos_fin = set()
        for h in historial_mecanicos_raw:
            m_id = h.get("mecanico_id")
            if m_id not in vistos_fin:
                vistos_fin.add(m_id)
                mecanicos_raw.append(h)

    estadias_raw = r.get("estadias_json") or []
    if isinstance(estadias_raw, str):
        estadias_raw = json.loads(estadias_raw)
    estadias_dtos = [
        EstadiaTallerDTO(**e) for e in estadias_raw if isinstance(e, dict)
    ]

    bus_en_taller = bool(r.get("bus_en_taller", False))
    horas_acum, total_vis = calcular_telemetria_estadias(
        estadias=estadias_dtos,
        horas_taller_acumuladas_db=r.get("horas_taller_acumuladas"),
        en_taller=bus_en_taller,
    )
    horas_en_taller_val = (
        horas_acum if total_vis > 0 else r.get("horas_en_taller")
    )

    return SolicitudDTO(
        id=r["id"],
        n_bus=r["n_bus"],
        bus_id=r.get("bus_id"),
        bus_patente=r.get("bus_patente"),
        usuario_creador_id=r.get("usuario_creador_id"),
        usuario_creador_nombre=r.get("usuario_creador_nombre"),
        usuario_creador_telefono=r.get("usuario_creador_telefono"),
        mecanico_cierre_id=r.get("mecanico_cierre_id"),
        mecanico_cierre_nombre=r.get("mecanico_cierre_nombre"),
        estado=r["estado"],
        descripcion_general=r.get("descripcion_general"),
        foto_url=storage.get_url(r.get("foto_url")),
        motivo_incompleto_checklist=r.get("motivo_incompleto_checklist"),
        motivo_cierre_parcial=r.get("motivo_cierre_parcial"),
        fecha_creacion=r["fecha_creacion"],
        fecha_actualizacion=r.get("fecha_actualizacion"),
        fecha_cierre=r.get("fecha_cierre"),
        fecha_liberacion=r.get("fecha_liberacion"),
        fecha_primer_ingreso_taller=r.get("fecha_primer_ingreso_taller"),
        horas_demora_primer_ingreso=(
            float(r["horas_demora_primer_ingreso"])
            if r.get("horas_demora_primer_ingreso") is not None
            else None
        ),
        horas_taller_acumuladas=horas_acum,
        total_visitas=total_vis,
        horas_en_taller=horas_en_taller_val,
        reincidencias_30d=r.get("reincidencias_30d", 0),
        pauta_completada=pauta_completada,
        total_fallas=tot,
        fallas_resueltas=resueltos,
        fallas_incompletas=incompletas,
        fallas_con_falta_repuesto=faltas,
        fallas_pendientes=pendientes,
        detalles=detalles_raw,
        mecanicos=mecanicos_raw,
        historial_mecanicos=historial_mecanicos_raw,
        comentarios=comentarios_raw,
        pauta_respuestas=pauta_respuestas_raw,
        evidencias=evidencias_dtos,
        estadias=estadias_dtos,
    )


def dict_to_solicitud_resumen_dto(
    r: dict, storage: StorageService = storage_service, mecanico_id: Optional[int] = None
) -> SolicitudResumenDTO:
    """Convierte una fila del listado de alta velocidad (1 sola consulta SQL) directamente a SolicitudResumenDTO."""
    estadias_raw = r.get("estadias_json") or []
    if isinstance(estadias_raw, str):
        try:
            estadias_raw = json.loads(estadias_raw)
        except Exception:
            estadias_raw = []
    estadias_dtos = [
        EstadiaTallerDTO(**e) for e in estadias_raw if isinstance(e, dict)
    ]

    bus_en_taller = bool(r.get("bus_en_taller", False))
    horas_acum, total_vis = calcular_telemetria_estadias(
        estadias=estadias_dtos,
        horas_taller_acumuladas_db=r.get("horas_taller_acumuladas"),
        en_taller=bus_en_taller,
    )
    horas_en_taller_val = (
        horas_acum if total_vis > 0 else r.get("horas_en_taller")
    )

    fecha_ingreso = r.get("fecha_primer_ingreso_taller") or r.get("fecha_creacion")

    detalles_raw = r.get("detalles_json") or []
    if isinstance(detalles_raw, str):
        try:
            detalles_raw = json.loads(detalles_raw)
        except Exception:
            detalles_raw = []

    if mecanico_id is not None:
        # En "mis-trabajos": contar fallas que el mecánico tiene asignadas activamente
        conteo_fallas = 0
        for d in detalles_raw:
            asigs = d.get("mecanicos_asignados") or []
            if isinstance(asigs, list) and any(
                isinstance(a, dict) and a.get("id") == mecanico_id for a in asigs
            ):
                conteo_fallas += 1
    else:
        # En "pendientes": contar todas las fallas que quedan disponibles (no resueltas)
        conteo_fallas = sum(1 for d in detalles_raw if not d.get("resuelto"))

    fecha_actualizacion = r.get("fecha_actualizacion") or r.get("fecha_creacion")

    return SolicitudResumenDTO(
        id=r["id"],
        estado=r["estado"],
        n_bus=r["n_bus"],
        fecha_ingreso=fecha_ingreso,
        fecha_actualizacion=fecha_actualizacion,
        chofer=r.get("usuario_creador_nombre"),
        tiempo_taller=horas_en_taller_val,
        numero_fallas=conteo_fallas,
    )


def orm_to_solicitud_resumen_dto(
    sol: Any, storage: StorageService = storage_service, mecanico_id: Optional[int] = None
) -> Optional[SolicitudResumenDTO]:
    """Mapea una entidad ORM TallerSolicitud a SolicitudResumenDTO sin disparar lazy loading síncrono."""
    if not sol:
        return None

    def _get_rel(obj, attr: str):
        if obj is None:
            return None
        return getattr(obj, "__dict__", {}).get(attr)

    bus_obj = _get_rel(sol, "bus")
    creador = _get_rel(sol, "creador")
    creador_nombre = creador.nombre_completo if creador else None

    estadias_dtos = []
    estadias_val = _get_rel(sol, "estadias") or []
    for est in estadias_val:
        estadias_dtos.append(
            EstadiaTallerDTO(
                id=est.id,
                solicitud_id=est.solicitud_id,
                numero_visita=est.numero_visita,
                fecha_ingreso=est.fecha_ingreso,
                fecha_salida=est.fecha_salida,
                horas_estadia=(
                    float(est.horas_estadia)
                    if est.horas_estadia is not None
                    else None
                ),
                motivo_salida=est.motivo_salida,
            )
        )

    bus_en_taller = bool(bus_obj.en_taller) if bus_obj else False
    horas_acum, total_vis = calcular_telemetria_estadias(
        estadias=estadias_dtos,
        horas_taller_acumuladas_db=getattr(sol, "horas_taller_acumuladas", 0.0),
        en_taller=bus_en_taller,
    )

    horas_en_taller_val = (
        horas_acum
        if total_vis > 0
        else calcular_horas_en_taller(sol.fecha_creacion, sol.fecha_cierre)
    )

    fecha_ingreso = getattr(sol, "fecha_primer_ingreso_taller", None) or sol.fecha_creacion
    fecha_actualizacion = getattr(sol, "fecha_actualizacion", None) or getattr(sol, "fecha_creacion", None)

    detalles_orm = _get_rel(sol, "detalles") or []
    if mecanico_id is not None:
        conteo_fallas = 0
        for det in detalles_orm:
            asigs = _get_rel(det, "asignaciones") or []
            if any(getattr(a, "mecanico_id", None) == mecanico_id and getattr(a, "is_activo", False) for a in asigs):
                conteo_fallas += 1
    else:
        conteo_fallas = sum(1 for det in detalles_orm if not getattr(det, "resuelto", False))

    return SolicitudResumenDTO(
        id=sol.id,
        estado=sol.estado,
        n_bus=sol.n_bus,
        fecha_ingreso=fecha_ingreso,
        fecha_actualizacion=fecha_actualizacion,
        chofer=creador_nombre,
        tiempo_taller=horas_en_taller_val,
        numero_fallas=conteo_fallas,
    )



def orm_to_solicitud_dto(
    sol: Any, storage: StorageService = storage_service
) -> Optional[SolicitudDTO]:
    """Mapea una entidad ORM TallerSolicitud a SolicitudDTO sin disparar lazy loading síncrono."""
    if not sol:
        return None

    def _get_rel(obj, attr: str):
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
        mec_resolvio_nombre = (
            mec_resolvio.nombre_completo if mec_resolvio else None
        )
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
        mecanicos_resolvieron = []
        vistos_resolutores = set()
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

            if det.resuelto and asig.resuelto_en_esta_asignacion and asig.mecanico_id not in vistos_resolutores:
                vistos_resolutores.add(asig.mecanico_id)
                mecanicos_resolvieron.append(
                    MecanicoResumenDTO(
                        id=asig.mecanico_id,
                        nombre=mec_nom or f"Mecánico #{asig.mecanico_id}",
                    )
                )

        if det.resuelto:
            if not mecanicos_resolvieron and det.mecanico_resolvio_id:
                u_res = _get_rel(det, "mecanico_resolvio")
                nom_res = u_res.nombre_completo if u_res else (mec_resolvio_nombre or f"Mecánico #{det.mecanico_resolvio_id}")
                mecanicos_resolvieron.append(
                    MecanicoResumenDTO(id=det.mecanico_resolvio_id, nombre=nom_res)
                )

            if mecanicos_resolvieron:
                mec_resolvio_nombre = ", ".join(m.nombre for m in mecanicos_resolvieron)
        else:
            mec_resolvio_nombre = None
            mecanicos_resolvieron = []

        detalles_dtos.append(
            SolicitudDetalleDTO(
                id=det.id,
                solicitud_id=det.solicitud_id,
                categoria_id=cat_id,
                categoria_nombre=cat_nombre,
                falla_id=det.falla_id,
                falla=falla_dto,
                descripcion_personalizada=det.descripcion_personalizada,
                estado=getattr(det, "estado", None) or ("RESUELTA" if det.resuelto else "PENDIENTE"),
                motivo_incompleto=getattr(det, "motivo_incompleto", None),
                resuelto=det.resuelto,
                mecanico_resolvio_id=det.mecanico_resolvio_id,
                mecanico_resolvio_nombre=mec_resolvio_nombre,
                mecanicos_resolvieron=mecanicos_resolvieron,
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
        usr_nombre = (
            usr.nombre_completo
            if usr
            else getattr(com, "_usuario_nombre_cached", None)
        )

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
    creador_telefono = getattr(creador, "telefono", None) if creador else None
    mec_cierre = _get_rel(sol, "mecanico_cierre")
    mecanico_cierre_nombre = (
        mec_cierre.nombre_completo
        if mec_cierre
        else getattr(sol, "_mecanico_cierre_nombre_cached", None)
    )
    bus_obj = _get_rel(sol, "bus")
    bus_patente = bus_obj.patente if bus_obj else None

    total_fallas = len(detalles_dtos)
    fallas_resueltas = len([d for d in detalles_dtos if d.estado == "RESUELTA" or d.resuelto])
    fallas_incompletas = len([d for d in detalles_dtos if d.estado == "INCOMPLETA"])
    fallas_con_falta_repuesto = len([d for d in detalles_dtos if d.falta_repuesto])
    fallas_pendientes = total_fallas - fallas_resueltas - fallas_incompletas

    evidencias_dtos = []
    evidencias_val = _get_rel(sol, "evidencias") or []
    for ev in evidencias_val:
        evidencias_dtos.append(
            SolicitudEvidenciaDTO(
                id=ev.id,
                solicitud_id=ev.solicitud_id,
                detalle_id=ev.detalle_id,
                usuario_id=ev.usuario_id,
                url=storage.get_url(ev.url) or ev.url,
                original_filename=ev.original_filename,
                size_bytes=ev.size_bytes,
                content_type=ev.content_type,
                fecha_creacion=ev.fecha_creacion,
            )
        )

    estadias_dtos = []
    estadias_val = _get_rel(sol, "estadias") or []
    for est in estadias_val:
        estadias_dtos.append(
            EstadiaTallerDTO(
                id=est.id,
                solicitud_id=est.solicitud_id,
                numero_visita=est.numero_visita,
                fecha_ingreso=est.fecha_ingreso,
                fecha_salida=est.fecha_salida,
                horas_estadia=(
                    float(est.horas_estadia)
                    if est.horas_estadia is not None
                    else None
                ),
                motivo_salida=est.motivo_salida,
            )
        )

    bus_en_taller = bool(bus_obj.en_taller) if bus_obj else False
    horas_acum, total_vis = calcular_telemetria_estadias(
        estadias=estadias_dtos,
        horas_taller_acumuladas_db=getattr(sol, "horas_taller_acumuladas", 0.0),
        en_taller=bus_en_taller,
    )

    horas_en_taller_val = (
        horas_acum
        if total_vis > 0
        else calcular_horas_en_taller(sol.fecha_creacion, sol.fecha_cierre)
    )

    return SolicitudDTO(
        id=sol.id,
        n_bus=sol.n_bus,
        bus_id=sol.bus_id,
        bus_patente=bus_patente,
        usuario_creador_id=sol.usuario_creador_id,
        usuario_creador_nombre=creador_nombre,
        usuario_creador_telefono=creador_telefono,
        mecanico_cierre_id=sol.mecanico_cierre_id,
        mecanico_cierre_nombre=mecanico_cierre_nombre,
        estado=sol.estado,
        descripcion_general=sol.descripcion_general,
        foto_url=storage.get_url(sol.foto_url),
        motivo_incompleto_checklist=getattr(sol, "motivo_incompleto_checklist", None),
        motivo_cierre_parcial=getattr(sol, "motivo_cierre_parcial", None),
        fecha_creacion=sol.fecha_creacion,
        fecha_actualizacion=getattr(sol, "fecha_actualizacion", None),
        fecha_cierre=sol.fecha_cierre,
        fecha_liberacion=getattr(sol, "fecha_liberacion", None),
        fecha_primer_ingreso_taller=getattr(sol, "fecha_primer_ingreso_taller", None),
        horas_demora_primer_ingreso=(
            float(sol.horas_demora_primer_ingreso)
            if getattr(sol, "horas_demora_primer_ingreso", None) is not None
            else None
        ),
        horas_taller_acumuladas=horas_acum,
        total_visitas=total_vis,
        horas_en_taller=horas_en_taller_val,
        reincidencias_30d=getattr(sol, "reincidencias_30d", 0),
        pauta_completada=len(pauta_dtos) >= TOTAL_ITEMS_PAUTA_PREVENTIVA,
        total_fallas=total_fallas,
        fallas_resueltas=fallas_resueltas,
        fallas_incompletas=fallas_incompletas,
        fallas_con_falta_repuesto=fallas_con_falta_repuesto,
        fallas_pendientes=fallas_pendientes,
        detalles=detalles_dtos,
        mecanicos=mecanicos_dtos,
        historial_mecanicos=historial_mecanicos_dtos,
        comentarios=comentarios_dtos,
        pauta_respuestas=pauta_dtos,
        evidencias=evidencias_dtos,
        estadias=estadias_dtos,
    )


def mapear_a_solicitud_dto(
    item: Any, storage: StorageService = storage_service
) -> Optional[SolicitudDTO]:
    """Mapea de forma segura un diccionario agregado (PostgreSQL JSON) o un modelo ORM a SolicitudDTO."""
    if item is None:
        return None
    if isinstance(item, dict):
        return dict_to_solicitud_dto(item, storage=storage)
    return orm_to_solicitud_dto(item, storage=storage)
