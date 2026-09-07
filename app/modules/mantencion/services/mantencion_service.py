import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.mantencion.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.mantencion.models.pauta_taller import TallerSolicitudPauta
from app.modules.mantencion.repository.mantencion_repository import (
    mantencion_repository,
    _calcular_duracion_minutos,
)
from app.modules.mantencion.dtos.mantencion_dto import (
    CategoriaFallaDTO,
    FallaTallerDTO,
    SolicitudDTO,
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
    TerminarAvanceDTO,
    ReportarRepuestoDTO,
    PautaTallerItemDTO,
    PautaRespuestaDTO,
    PautaBatchUpdateDTO,
    PautaEstadoResumenDTO,
    LiberarSolicitudDTO,
    AgregarFallaDTO,
)

logger = logging.getLogger(__name__)


def _describir_detalle(det: TallerSolicitudDetalle) -> str:
    """Retorna una descripción legible para humanos de la avería, sin exponer IDs técnicos ni disparar lazy loads."""
    if not det:
        return "Avería general"
    desc_pers = det.descripcion_personalizada.strip() if getattr(det, "descripcion_personalizada", None) else None

    # Acceder a través de __dict__ evita disparar lazy-loads síncronos en asyncpg/aiosqlite
    falla_obj = det.__dict__.get("falla") if hasattr(det, "__dict__") else None
    nom_falla = getattr(falla_obj, "nombre", None) if falla_obj else None

    nom_cat = None
    if falla_obj and hasattr(falla_obj, "__dict__"):
        cat_obj = falla_obj.__dict__.get("categoria")
        if cat_obj:
            nom_cat = getattr(cat_obj, "nombre", None)

    if nom_falla and desc_pers:
        return f"{nom_falla} ({desc_pers})"
    elif nom_falla:
        return nom_falla
    elif desc_pers:
        return desc_pers
    elif nom_cat:
        return f"Avería de {nom_cat}"
    return "Avería general"


class MantencionService:
    """
    Capa de servicio de negocio / Casos de Uso para el módulo de Taller de Mantención.
    Responsabilidad exclusiva: Validaciones de reglas operacionales, orquestación de pasos,
    transformación a DTOs y control transaccional (commit/rollback).
    """

    def _to_solicitud_dto(self, sol) -> Optional[SolicitudDTO]:
        if not sol:
            return None

        detalles_dtos = []
        for det in sol.detalles:
            falla_dto = None
            cat_id = None
            cat_nombre = None
            if det.falla:
                cat_dto = None
                if det.falla.categoria:
                    cat_id = det.falla.categoria.id
                    cat_nombre = det.falla.categoria.nombre
                    cat_dto = CategoriaFallaDTO(
                        id=det.falla.categoria.id,
                        nombre=det.falla.categoria.nombre,
                        is_active=det.falla.categoria.is_active,
                    )
                falla_dto = FallaTallerDTO(
                    id=det.falla.id,
                    categoria_id=det.falla.categoria_id,
                    nombre=det.falla.nombre,
                    is_active=det.falla.is_active,
                    categoria=cat_dto,
                )

            mec_resolvio_nombre = det.mecanico_resolvio.nombre_completo if det.mecanico_resolvio else None

            mecanicos_asignados = []
            historial_asignaciones = []
            mecs_asig_vistos = set()
            if hasattr(det, "asignaciones") and det.asignaciones:
                for asig in det.asignaciones:
                    mec_nom = asig.mecanico.nombre_completo if asig.mecanico else None
                    asig_por_nom = asig.asignado_por.nombre_completo if asig.asignado_por else None

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

        if hasattr(sol, "mecanicos") and sol.mecanicos:
            for mec in sol.mecanicos:
                mec_nombre = mec.mecanico.nombre_completo if mec.mecanico else None

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
        if hasattr(sol, "detalles") and sol.detalles:
            for det in sol.detalles:
                if hasattr(det, "asignaciones") and det.asignaciones:
                    for asig in det.asignaciones:
                        if getattr(asig, "is_activo", False) and asig.mecanico_id not in mecanicos_activos_ids:
                            mecanicos_activos_ids.add(asig.mecanico_id)
                            mec_nom = asig.mecanico.nombre_completo if asig.mecanico else None
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
        for com in sol.comentarios:
            usr_nombre = com.usuario.nombre_completo if com.usuario else None

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
        if hasattr(sol, "pauta_respuestas") and sol.pauta_respuestas:
            for pr in sol.pauta_respuestas:
                item_cat = pr.item.categoria if pr.item else None
                item_nom = pr.item.item if pr.item else None
                mec_nom = pr.mecanico.nombre_completo if pr.mecanico else None
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

        creador_nombre = sol.creador.nombre_completo if sol.creador else None
        mecanico_cierre_nombre = sol.mecanico_cierre.nombre_completo if sol.mecanico_cierre else None
        bus_patente = sol.bus.patente if sol.bus else None

        total_fallas = len(detalles_dtos)
        fallas_resueltas = len([d for d in detalles_dtos if d.resuelto])
        fallas_con_falta_repuesto = len([d for d in detalles_dtos if d.falta_repuesto])

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
            foto_url=sol.foto_url,
            motivo_incompleto_checklist=getattr(sol, "motivo_incompleto_checklist", None),
            motivo_cierre_parcial=getattr(sol, "motivo_cierre_parcial", None),
            fecha_creacion=sol.fecha_creacion,
            fecha_cierre=sol.fecha_cierre,
            pauta_completada=len(pauta_dtos) >= 11,
            total_fallas=total_fallas,
            fallas_resueltas=fallas_resueltas,
            fallas_con_falta_repuesto=fallas_con_falta_repuesto,
            detalles=detalles_dtos,
            mecanicos=mecanicos_dtos,
            historial_mecanicos=historial_mecanicos_dtos,
            comentarios=comentarios_dtos,
            pauta_respuestas=pauta_dtos,
        )

    # --- Consultas de Catálogos ---

    async def get_categorias(self, db: AsyncSession) -> List[CategoriaFallaDTO]:
        cats = await mantencion_repository.get_categorias(db)
        return [CategoriaFallaDTO.model_validate(c) for c in cats]

    async def get_fallas(self, db: AsyncSession, categoria_id: Optional[int] = None) -> List[FallaTallerDTO]:
        fallas = await mantencion_repository.get_fallas(db, categoria_id)
        res = []
        for f in fallas:
            cat_dto = None
            if f.categoria:
                cat_dto = CategoriaFallaDTO(id=f.categoria.id, nombre=f.categoria.nombre, is_active=f.categoria.is_active)
            res.append(FallaTallerDTO(id=f.id, categoria_id=f.categoria_id, nombre=f.nombre, is_active=f.is_active, categoria=cat_dto))
        return res

    async def get_solicitud(self, db: AsyncSession, solicitud_id: int) -> SolicitudDTO:
        logger.debug("[MANTENCION] Consultando solicitud | id=%s", solicitud_id)
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not sol:
            raise NotFoundException("Solicitud de taller no encontrada")
        return self._to_solicitud_dto(sol)

    async def list_pendientes(self, db: AsyncSession) -> List[SolicitudDTO]:
        logger.debug("[MANTENCION] Listando solicitudes pendientes")
        solicitudes = await mantencion_repository.list_pendientes(db)
        return [self._to_solicitud_dto(s) for s in solicitudes]

    async def list_mis_trabajos(self, db: AsyncSession, mecanico_id: int) -> List[SolicitudDTO]:
        logger.debug("[MANTENCION] Listando trabajos activos | mecanico_id=%s", mecanico_id)
        solicitudes = await mantencion_repository.list_mis_trabajos(db, mecanico_id)
        return [self._to_solicitud_dto(s) for s in solicitudes]

    async def list_auditoria(self, db: AsyncSession) -> List[SolicitudDTO]:
        logger.debug("[MANTENCION] Consultando auditoría completa de solicitudes")
        solicitudes = await mantencion_repository.list_auditoria(db)
        return [self._to_solicitud_dto(s) for s in solicitudes]

    # --- Casos de Uso Operacionales y Transaccionales ---

    async def create_solicitud(self, db: AsyncSession, dto: SolicitudCreateDTO, creador_id: int) -> SolicitudDTO:
        logger.info("[MANTENCION] Creando solicitud | n_bus='%s' | creador_id=%s", dto.n_bus, creador_id)

        bus_id = dto.bus_id
        if not bus_id and dto.n_bus:
            bus_id = await mantencion_repository.get_bus_id_by_n_bus(db, dto.n_bus)

        solicitud = TallerSolicitud(
            n_bus=dto.n_bus,
            bus_id=bus_id,
            usuario_creador_id=creador_id,
            estado="REPORTADO",
            descripcion_general=dto.descripcion_general,
            foto_url=dto.foto_url,
            fecha_creacion=datetime.now(),
        )
        mantencion_repository.add_solicitud(db, solicitud)
        await mantencion_repository.flush(db)

        if dto.detalles:
            for det_dto in dto.detalles:
                falla_id = det_dto.falla_id
                if not falla_id and det_dto.categoria_id:
                    falla_id = await mantencion_repository.find_falla_activa_by_categoria(db, det_dto.categoria_id)
                    if not falla_id:
                        cat = await mantencion_repository.get_categoria_by_id(db, det_dto.categoria_id)
                        cat_nom = cat.nombre if cat else f"Categoría #{det_dto.categoria_id}"
                        nueva_falla = FallaTaller(
                            categoria_id=det_dto.categoria_id,
                            nombre=f"Avería de {cat_nom}",
                            is_active=True,
                        )
                        mantencion_repository.add_falla(db, nueva_falla)
                        await mantencion_repository.flush(db)
                        falla_id = nueva_falla.id

                detalle = TallerSolicitudDetalle(
                    solicitud_id=solicitud.id,
                    falla_id=falla_id,
                    descripcion_personalizada=det_dto.descripcion_personalizada,
                    resuelto=False,
                    fecha_creacion=datetime.now(),
                )
                mantencion_repository.add_detalle(db, detalle)

        await db.commit()
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud.id)
        logger.info("[MANTENCION] Solicitud creada | id=%s | n_bus='%s' | estado=REPORTADO", sol.id, sol.n_bus)
        return self._to_solicitud_dto(sol)

    async def tomar_trabajo(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: int, dto: TomarTrabajoDTO
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Tomar trabajo | solicitud_id=%s | mecanico_id=%s | colaboradores=%s", solicitud_id, mecanico_id, dto.colaboradores_ids)
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        # 1. Marcar mecánicos previos como inactivos de forma atómica en el repositorio
        await mantencion_repository.desactivar_mecanicos_activos(
            db, solicitud_id=solicitud.id, fecha_desasignacion=now
        )

        # 2. Asignar mecánico que toma el trabajo (co-responsabilidad horizontal)
        mecanico_entry = TallerSolicitudMecanico(
            solicitud_id=solicitud.id,
            mecanico_id=mecanico_id,
            es_lider_responsable=False,
            is_activo=True,
            fecha_asignacion=now,
        )
        mantencion_repository.add_mecanico(db, mecanico_entry)
        logger.info("[MANTENCION] Mecánico asignado a solicitud | solicitud_id=%s | mecanico_id=%s", solicitud_id, mecanico_id)

        # 3. Asignar colaboradores si fueron seleccionados (por IDs o por Nombres)
        target_colab_ids = set(dto.colaboradores_ids or [])
        if dto.colaboradores_nombres:
            from app.modules.auth.repository.user_repository import user_repository
            colab_users = await user_repository.get_mecanicos_by_nombres_o_usernames(db, dto.colaboradores_nombres)
            for u in colab_users:
                target_colab_ids.add(u.id)

        for colab_id in target_colab_ids:
            if colab_id != mecanico_id:
                colab_entry = TallerSolicitudMecanico(
                    solicitud_id=solicitud.id,
                    mecanico_id=colab_id,
                    es_lider_responsable=False,
                    is_activo=True,
                    fecha_asignacion=now,
                )
                mantencion_repository.add_mecanico(db, colab_entry)
                logger.info("[MANTENCION] Colaborador co-responsable asignado | solicitud_id=%s | colab_id=%s", solicitud_id, colab_id)

        # 4. Actualizar estado
        solicitud.estado = "EN_REPARACION"

        # 5. Agregar comentario predeterminado de inicio/asignación
        u_mec = await mantencion_repository.get_usuario_by_id(db, mecanico_id)
        mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"

        colab_nombres = []
        for colab_id in target_colab_ids:
            if colab_id != mecanico_id:
                u_c = await mantencion_repository.get_usuario_by_id(db, colab_id)
                if u_c:
                    colab_nombres.append(u_c.nombre_completo)

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
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        logger.info("[MANTENCION] Solicitud en reparación | id=%s | estado=EN_REPARACION", sol.id)
        return self._to_solicitud_dto(sol)

    async def agregar_colaborador(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: int, dto: AgregarColaboradorDTO
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Agregando colaborador en caliente | solicitud_id=%s | solicitado_por=%s", solicitud_id, mecanico_id)
        from app.modules.auth.repository.user_repository import user_repository

        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
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
        mantencion_repository.add_mecanico(db, colab_entry)

        await db.commit()
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def desasignar_mecanico(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: int, comentario: Optional[str] = None
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Desasignando mecánico | solicitud_id=%s | mecanico_id=%s", solicitud_id, mecanico_id)
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        mecanico_entry = None
        for mec in solicitud.mecanicos:
            if mec.mecanico_id == mecanico_id and mec.is_activo:
                mecanico_entry = mec
                break

        if not mecanico_entry:
            logger.warning("[MANTENCION] Desasignación fallida: mecánico no activo | solicitud_id=%s | mecanico_id=%s", solicitud_id, mecanico_id)
            raise BusinessRuleException("El mecánico no está asignado activamente a esta solicitud")

        now = datetime.now()
        mecanico_entry.is_activo = False
        mecanico_entry.fecha_desasignacion = now

        u_mec = await mantencion_repository.get_usuario_by_id(db, mecanico_id)
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
        mantencion_repository.add_comentario(db, comentario_entry)

        activos = [m for m in solicitud.mecanicos if m.is_activo and m.id != mecanico_entry.id]

        if not activos:
            solicitud.estado = "PENDIENTE_REASIGNACION"
            logger.info("[MANTENCION] Sin mecánicos activos → PENDIENTE_REASIGNACION | solicitud_id=%s", solicitud_id)

        await db.commit()
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def liberar_turno(
        self, db: AsyncSession, solicitud_id: int, usuario_id: int, dto: LiberarTurnoDTO
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Liberar turno | solicitud_id=%s | usuario_id=%s", solicitud_id, usuario_id)
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()
        await mantencion_repository.desactivar_mecanicos_activos(
            db, solicitud_id=solicitud.id, fecha_desasignacion=now
        )

        solicitud.estado = "PENDIENTE_REASIGNACION"

        u_usr = await mantencion_repository.get_usuario_by_id(db, usuario_id)
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
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def check_detalle(
        self, db: AsyncSession, solicitud_id: int, detalle_id: int, mecanico_id: int, resuelto: bool
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Check detalle | solicitud_id=%s | detalle_id=%s | mecanico_id=%s | resuelto=%s", solicitud_id, detalle_id, mecanico_id, resuelto)
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        detalle_target = None
        for det in solicitud.detalles:
            if det.id == detalle_id:
                detalle_target = det
                break

        if not detalle_target:
            raise NotFoundException("Detalle de falla no encontrado")

        if resuelto and getattr(detalle_target, "falta_repuesto", False):
            raise BusinessRuleException(
                "No se puede marcar como resuelta una falla que se encuentra a la espera de repuesto. "
                "Debe registrarse primero la recepción/disponibilidad del repuesto."
            )

        now = datetime.now()
        detalle_target.resuelto = resuelto
        if resuelto:
            detalle_target.mecanico_resolvio_id = mecanico_id
            detalle_target.fecha_resolucion = now
        else:
            detalle_target.mecanico_resolvio_id = None
            detalle_target.fecha_resolucion = None

        u_mec = await mantencion_repository.get_usuario_by_id(db, mecanico_id)
        mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"
        falla_nom = _describir_detalle(detalle_target)

        if resuelto:
            texto_check = f"{mec_nom} completó la reparación de la falla: '{falla_nom}'"
            tipo_check = "RESOLUCION"
        else:
            texto_check = f"{mec_nom} reabrió la falla: '{falla_nom}'"
            tipo_check = "REAPERTURA"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo=tipo_check,
            comentario=texto_check,
            fecha_registro=now,
        )
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def agregar_comentario(
        self, db: AsyncSession, solicitud_id: int, usuario_id: int, dto: ComentarioCreateDTO
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Agregando comentario | solicitud_id=%s | usuario_id=%s | tipo=%s", solicitud_id, usuario_id, dto.tipo)
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=usuario_id,
            tipo=dto.tipo if dto.tipo else "GENERAL",
            comentario=dto.comentario,
            fecha_registro=datetime.now(),
        )
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def finalizar_solicitud(
        self, db: AsyncSession, solicitud_id: int, mecanico_cierre_id: int, dto: FinalizarSolicitudDTO
    ) -> SolicitudDTO:
        logger.info("[MANTENCION] Finalizando solicitud | id=%s | mecanico_cierre_id=%s", solicitud_id, mecanico_cierre_id)
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        # 1. Validar Checklist / Pauta de Taller Preventiva
        items_activos = await mantencion_repository.get_pauta_items(db)
        total_items_pauta = len(items_activos)

        respuestas_registradas = await mantencion_repository.get_pauta_respuestas_by_solicitud(db, solicitud_id)
        items_respondidos = len(respuestas_registradas)

        if total_items_pauta > 0 and items_respondidos < total_items_pauta:
            if not (dto.motivo_incompleto_checklist and dto.motivo_incompleto_checklist.strip()):
                raise BusinessRuleException(
                    f"La pauta preventiva está incompleta ({items_respondidos}/{total_items_pauta} ítems respondidos). "
                    "Debe completar la pauta o ingresar una justificación en 'motivo_incompleto_checklist'."
                )
            solicitud.motivo_incompleto_checklist = dto.motivo_incompleto_checklist.strip()
        else:
            solicitud.motivo_incompleto_checklist = dto.motivo_incompleto_checklist

        # 2. Validar Cierre Parcial / Fallas no resueltas o falta de repuesto
        fallas_no_resueltas = [
            d for d in solicitud.detalles if not d.resuelto or getattr(d, "falta_repuesto", False)
        ]
        if fallas_no_resueltas:
            if not (dto.motivo_cierre_parcial and dto.motivo_cierre_parcial.strip()):
                raise BusinessRuleException(
                    f"Existen {len(fallas_no_resueltas)} falla(s) no resueltas o con falta de repuestos. "
                    "Para liberar el bus con cierre parcial, debe ingresar una justificación en 'motivo_cierre_parcial'."
                )
            solicitud.motivo_cierre_parcial = dto.motivo_cierre_parcial.strip()
        else:
            solicitud.motivo_cierre_parcial = dto.motivo_cierre_parcial

        solicitud.estado = "FINALIZADO"
        solicitud.mecanico_cierre_id = mecanico_cierre_id
        solicitud.fecha_cierre = now

        # 3. Marcar mecánicos y asignaciones activas como completadas
        for mec in solicitud.mecanicos:
            if mec.is_activo:
                mec.is_activo = False
                mec.fecha_desasignacion = now
                if mec.fecha_asignacion:
                    mec.duracion_minutos = _calcular_duracion_minutos(mec.fecha_asignacion, now)

        asigs_activas = await mantencion_repository.get_asignaciones_activas(db, solicitud_id)
        for asig in asigs_activas:
            asig.is_activo = False
            asig.fecha_desasignacion = now
            if asig.fecha_asignacion:
                asig.duracion_minutos = _calcular_duracion_minutos(asig.fecha_asignacion, now)

        # 4. Liberar bus del taller si corresponde
        if dto.liberar_bus_taller and solicitud.bus_id:
            bus = await mantencion_repository.get_bus_by_id(db, solicitud.bus_id)
            if bus:
                bus.en_taller = False

        # 5. Registrar comentario de cierre en bitácora
        u_cierre = await mantencion_repository.get_usuario_by_id(db, mecanico_cierre_id)
        mec_cierre_nom = u_cierre.nombre_completo if u_cierre else "Mecánico"

        if dto.liberar_bus_taller:
            texto_cierre = f"{mec_cierre_nom} finalizó los trabajos de la OT y liberó el bus para operaciones."
        else:
            texto_cierre = f"{mec_cierre_nom} finalizó los trabajos de la OT (el bus permanece en taller)."

        if dto.comentario_cierre and dto.comentario_cierre.strip():
            texto_cierre += f" Comentario de cierre: {dto.comentario_cierre.strip()}."
        if solicitud.motivo_cierre_parcial:
            texto_cierre += f" Motivo cierre parcial: {solicitud.motivo_cierre_parcial}."
        if solicitud.motivo_incompleto_checklist:
            texto_cierre += f" Justificación pauta preventiva: {solicitud.motivo_incompleto_checklist}."

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_cierre_id,
            tipo="CIERRE",
            comentario=texto_cierre,
            fecha_registro=now,
        )
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Solicitud FINALIZADA | id=%s, bus_id=%s, bus_liberado=%s",
            solicitud.id,
            solicitud.bus_id,
            dto.liberar_bus_taller,
        )
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def autoasignar_fallas(
        self, db: AsyncSession, solicitud_id: int, dto: AutoasignarFallasDTO, mecanico_id: int
    ) -> SolicitudDTO:
        logger.info(
            "[MANTENCION] Autoasignando fallas atómicas | solicitud_id=%s, mecanico_id=%s, fallas=%s, colaboradores=%s",
            solicitud_id,
            mecanico_id,
            dto.detalles_ids,
            dto.colaboradores_ids,
        )
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
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

        asigs_exist = await mantencion_repository.get_asignaciones_activas(
            db, solicitud_id=solicitud_id, detalles_ids=dto.detalles_ids, mecanicos_ids=mecanicos_objetivo
        )
        activas_existentes = {(a.mecanico_id, a.detalle_id) for a in asigs_exist}

        for m_id in mecanicos_objetivo:
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
                mantencion_repository.add_asignacion_falla(db, nueva_asig)
                asignadas_count += 1

            presencia = await mantencion_repository.get_presencia_activa_individual(db, solicitud_id, m_id)
            if not presencia:
                nueva_presencia = TallerSolicitudMecanico(
                    solicitud_id=solicitud_id,
                    mecanico_id=m_id,
                    asignado_por_id=mecanico_id,
                    es_lider_responsable=False,
                    is_activo=True,
                    fecha_asignacion=now,
                )
                mantencion_repository.add_mecanico(db, nueva_presencia)

        if solicitud.estado in ["REPORTADO", "PENDIENTE", "PENDIENTE_REASIGNACION"]:
            solicitud.estado = "EN_REPARACION"

        u_mec = await mantencion_repository.get_usuario_by_id(db, mecanico_id)
        mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"

        colab_nombres = []
        if dto.colaboradores_ids:
            for c_id in dto.colaboradores_ids:
                if c_id != mecanico_id:
                    u_c = await mantencion_repository.get_usuario_by_id(db, c_id)
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
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Fallas autoasignadas | solicitud_id=%s, mecanico_id=%s, count=%s",
            solicitud_id,
            mecanico_id,
            asignadas_count,
        )
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

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
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
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

        asigs_exist = await mantencion_repository.get_asignaciones_activas(
            db, solicitud_id=solicitud_id, detalles_ids=dto.detalles_ids, mecanicos_ids=[dto.mecanico_id]
        )
        activas_existentes = {a.detalle_id for a in asigs_exist}

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
            mantencion_repository.add_asignacion_falla(db, nueva_asig)
            asignadas_count += 1

        presencia = await mantencion_repository.get_presencia_activa_individual(db, solicitud_id, dto.mecanico_id)
        if not presencia:
            nueva_presencia = TallerSolicitudMecanico(
                solicitud_id=solicitud_id,
                mecanico_id=dto.mecanico_id,
                asignado_por_id=supervisor_id,
                es_lider_responsable=False,
                is_activo=True,
                fecha_asignacion=now,
            )
            mantencion_repository.add_mecanico(db, nueva_presencia)

        if solicitud.estado in ["REPORTADO", "PENDIENTE", "PENDIENTE_REASIGNACION"]:
            solicitud.estado = "EN_REPARACION"

        u_sup = await mantencion_repository.get_usuario_by_id(db, supervisor_id)
        sup_nom = u_sup.nombre_completo if u_sup else "Supervisión"

        u_mec = await mantencion_repository.get_usuario_by_id(db, dto.mecanico_id)
        mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"

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
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Supervisora asignó fallas | solicitud_id=%s, supervisor_id=%s, mecanico_id=%s, count=%s",
            solicitud_id,
            supervisor_id,
            dto.mecanico_id,
            asignadas_count,
        )
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def terminar_avance(
        self, db: AsyncSession, solicitud_id: int, dto: TerminarAvanceDTO, mecanico_id: int
    ) -> SolicitudDTO:
        logger.info(
            "[MANTENCION] Registrando término de avance | solicitud_id=%s, mecanico_id=%s, fallas=%s",
            solicitud_id,
            mecanico_id,
            dto.detalles_ids,
        )
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        asignaciones_activas = await mantencion_repository.get_asignaciones_activas(
            db, solicitud_id=solicitud_id, detalles_ids=dto.detalles_ids
        )
        presencias_activas = await mantencion_repository.get_presencias_activas(db, solicitud_id=solicitud_id)

        if not asignaciones_activas and not presencias_activas:
            raise BusinessRuleException("No hay asignaciones ni mecánicos activos para finalizar avance en esta solicitud")

        sol_detalles_map = {d.id: d for d in solicitud.detalles}
        mecanicos_involucrados_ids = set()
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
            mecanicos_involucrados_ids.add(asig.mecanico_id)
            cerradas_asig_ids.add(asig.id)

        con_restantes_ids = set()
        if dto.detalles_ids and cerradas_asig_ids:
            con_restantes_ids = await mantencion_repository.get_asignaciones_activas_restantes(
                db, solicitud_id, mecanicos_involucrados_ids, cerradas_asig_ids
            )

        presencias_cerradas_ids = set()
        for p in presencias_activas:
            mecanicos_involucrados_ids.add(p.mecanico_id)
            if p.mecanico_id not in con_restantes_ids:
                p.is_activo = False
                p.fecha_desasignacion = now
                if p.fecha_asignacion:
                    p.duracion_minutos = _calcular_duracion_minutos(p.fecha_asignacion, now)
                presencias_cerradas_ids.add(p.id)

        quedan_presencias = any(p.is_activo for p in presencias_activas if p.id not in presencias_cerradas_ids)

        if dto.detalles_ids and cerradas_asig_ids:
            quedan_asignaciones = await mantencion_repository.get_otras_asignaciones_activas(
                db, solicitud_id, cerradas_asig_ids
            )
        else:
            quedan_asignaciones = False

        if not quedan_presencias and not quedan_asignaciones:
            solicitud.estado = "PENDIENTE"
            logger.info("[MANTENCION] Solicitud sin cuadrilla activa → PENDIENTE | solicitud_id=%s", solicitud_id)

        await mantencion_repository.flush(db)

        mecanicos_nombres = []
        for m_id in sorted(mecanicos_involucrados_ids):
            u = await mantencion_repository.get_usuario_by_id(db, m_id)
            mecanicos_nombres.append(u.nombre_completo if u else "Mecánico")

        u_ejecutor = await mantencion_repository.get_usuario_by_id(db, mecanico_id)
        ejecutor_nombre = u_ejecutor.nombre_completo if u_ejecutor else "Mecánico"

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
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Avance finalizado (grupal/individual) | solicitud_id=%s, ejecutado_por=%s, involucrados=%s, estado_final=%s",
            solicitud_id,
            mecanico_id,
            list(mecanicos_involucrados_ids),
            solicitud.estado,
        )
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def reportar_repuesto(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        dto: ReportarRepuestoDTO,
        mecanico_id: int,
    ) -> SolicitudDTO:
        logger.info(
            "[MANTENCION] Reportando repuesto | solicitud_id=%s, detalle_id=%s, falta=%s",
            solicitud_id,
            detalle_id,
            dto.falta_repuesto,
        )
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        detalle = next((d for d in solicitud.detalles if d.id == detalle_id), None)
        if not detalle:
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

        u_mec = await mantencion_repository.get_usuario_by_id(db, mecanico_id)
        mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"
        falla_nom = _describir_detalle(detalle)
        estado_str = "FALTA DE REPUESTO" if dto.falta_repuesto else "REPUESTO DISPONIBLE"

        texto = f"{mec_nom} reportó {estado_str} para la falla: '{falla_nom}'"
        if dto.comentario and dto.comentario.strip():
            texto += f" - Detalle: {dto.comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo=tipo_accion,
            comentario=texto,
            fecha_registro=now,
        )
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Reporte de repuesto | solicitud_id=%s, detalle_id=%s, falta_repuesto=%s",
            solicitud_id,
            detalle_id,
            dto.falta_repuesto,
        )
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def get_pauta_items(self, db: AsyncSession) -> List[PautaTallerItemDTO]:
        items = await mantencion_repository.get_pauta_items(db)
        return [PautaTallerItemDTO.model_validate(it) for it in items]

    async def get_pauta_resumen(
        self, db: AsyncSession, solicitud_id: int
    ) -> PautaEstadoResumenDTO:
        items = await mantencion_repository.get_pauta_items(db)
        total_items = len(items)

        respuestas_orm = await mantencion_repository.get_pauta_respuestas_by_solicitud(
            db, solicitud_id
        )

        resp_dtos = []
        defectos_count = 0
        for r in respuestas_orm:
            if r.estado == "DEFECTO":
                defectos_count += 1
            cat = r.item.categoria if r.item else None
            nom = r.item.item if r.item else None
            mec_nom = (
                f"{r.mecanico.nombre or ''} {r.mecanico.apellido or ''}".strip()
                if r.mecanico
                else None
            )
            resp_dtos.append(
                PautaRespuestaDTO(
                    id=r.id,
                    solicitud_id=r.solicitud_id,
                    item_id=r.item_id,
                    item_categoria=cat,
                    item_nombre=nom,
                    estado=r.estado,
                    observacion=r.observacion,
                    mecanico_id=r.mecanico_id,
                    mecanico_nombre=mec_nom,
                    fecha_registro=r.fecha_registro,
                )
            )

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
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if not dto.respuestas:
            raise BusinessRuleException("Debe enviar al menos una respuesta de pauta")

        now = datetime.now()

        item_ids = [r.item_id for r in dto.respuestas]
        valid_item_ids = await mantencion_repository.get_pauta_items_by_ids(db, item_ids)

        respuestas_previas = await mantencion_repository.get_pauta_respuestas_by_solicitud(db, solicitud_id)
        existentes_map = {r.item_id: r for r in respuestas_previas}

        for r_dto in dto.respuestas:
            if r_dto.item_id not in valid_item_ids:
                raise NotFoundException(f"Ítem de pauta con ID {r_dto.item_id} no existe")

            if r_dto.item_id in existentes_map:
                obj = existentes_map[r_dto.item_id]
                obj.estado = r_dto.estado
                obj.observacion = r_dto.observacion
                obj.mecanico_id = mecanico_id
                obj.fecha_registro = now
            else:
                nuevo = TallerSolicitudPauta(
                    solicitud_id=solicitud_id,
                    item_id=r_dto.item_id,
                    estado=r_dto.estado,
                    observacion=r_dto.observacion,
                    mecanico_id=mecanico_id,
                    fecha_registro=now,
                )
                mantencion_repository.add_pauta_respuesta(db, nuevo)

        u_mec = await mantencion_repository.get_usuario_by_id(db, mecanico_id)
        mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="CHECKLIST",
            comentario=f"{mec_nom} registró/actualizó {len(dto.respuestas)} ítem(s) de la pauta preventiva",
            fecha_registro=now,
        )
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        return await self.get_pauta_resumen(db, solicitud_id)

    async def liberar_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: LiberarSolicitudDTO,
        mecanico_id: int,
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
        solicitud = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if solicitud.estado == "FINALIZADO":
            raise BusinessRuleException("No se pueden agregar fallas a una solicitud que ya ha sido finalizada")

        now = datetime.now()
        falla_id = dto.falla_id

        # 1. Resolver falla_id si se envió categoria_id
        if not falla_id and dto.categoria_id:
            falla_id = await mantencion_repository.find_falla_activa_by_categoria(db, dto.categoria_id)
            if not falla_id:
                cat = await mantencion_repository.get_categoria_by_id(db, dto.categoria_id)
                cat_nom = cat.nombre if cat else f"Categoría #{dto.categoria_id}"
                nueva_falla = FallaTaller(
                    categoria_id=dto.categoria_id,
                    nombre=f"Avería de {cat_nom}",
                    is_active=True,
                )
                mantencion_repository.add_falla(db, nueva_falla)
                await mantencion_repository.flush(db)
                falla_id = nueva_falla.id
        elif not falla_id and not dto.categoria_id:
            if not dto.descripcion_personalizada or not dto.descripcion_personalizada.strip():
                raise BusinessRuleException("Debe indicar al menos una categoría, falla o descripción personalizada de la avería")
            falla_id = await mantencion_repository.find_falla_otro(db)

        # 2. Crear nuevo detalle de falla
        nuevo_detalle = TallerSolicitudDetalle(
            solicitud_id=solicitud.id,
            falla_id=falla_id,
            descripcion_personalizada=dto.descripcion_personalizada.strip() if dto.descripcion_personalizada else None,
            resuelto=False,
            falta_repuesto=False,
            fecha_creacion=now,
        )
        mantencion_repository.add_detalle(db, nuevo_detalle)
        await mantencion_repository.flush(db)

        # 3. Autoasignación si corresponde
        if dto.autoasignar:
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
            mantencion_repository.add_asignacion_falla(db, nueva_asig)

            presencia = await mantencion_repository.get_presencia_activa_individual(db, solicitud.id, mecanico_id)
            if not presencia:
                mantencion_repository.add_mecanico(
                    db,
                    TallerSolicitudMecanico(
                        solicitud_id=solicitud.id,
                        mecanico_id=mecanico_id,
                        asignado_por_id=mecanico_id,
                        es_lider_responsable=False,
                        is_activo=True,
                        fecha_asignacion=now,
                    )
                )

            if solicitud.estado in ["REPORTADO", "PENDIENTE", "PENDIENTE_REASIGNACION"]:
                solicitud.estado = "EN_REPARACION"

        # 4. Registrar en bitácora inmutable
        u = await mantencion_repository.get_usuario_by_id(db, mecanico_id)
        mec_nombre = u.nombre_completo if u else "Mecánico"

        desc_pers = dto.descripcion_personalizada.strip() if dto.descripcion_personalizada else None
        nom_falla_o_cat = None
        if falla_id:
            f_obj = await mantencion_repository.get_falla_by_id(db, falla_id)
            if f_obj:
                nom_falla_o_cat = f_obj.nombre
        elif dto.categoria_id:
            c_obj = await mantencion_repository.get_categoria_by_id(db, dto.categoria_id)
            if c_obj:
                nom_falla_o_cat = f"Avería de {c_obj.nombre}"

        if nom_falla_o_cat and desc_pers:
            falla_txt = f"{nom_falla_o_cat} ({desc_pers})"
        elif nom_falla_o_cat:
            falla_txt = nom_falla_o_cat
        elif desc_pers:
            falla_txt = desc_pers
        else:
            falla_txt = "Avería general"

        texto_bitacora = f"{mec_nombre} detectó y agregó una nueva avería a la orden: '{falla_txt}'"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="AVANCE",
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        mantencion_repository.add_comentario(db, comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Nueva avería agregada a solicitud #%s por mecánico #%s | detalle_id=%s, autoasignar=%s",
            solicitud_id,
            mecanico_id,
            nuevo_detalle.id,
            dto.autoasignar,
        )
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)


mantencion_service = MantencionService()
