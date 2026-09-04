import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mantencion.repository.mantencion_repository import mantencion_repository
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


class MantencionService:
    """
    Servicio de capa de negocio para transformar modelos ORM en DTOs y validar reglas operacionales.
    """

    def _to_solicitud_dto(self, sol) -> SolicitudDTO:
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
                    if asig.is_activo:
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
        for mec in sol.mecanicos:
            mec_nombre = mec.mecanico.nombre_completo if mec.mecanico else None

            mecanicos_dtos.append(
                SolicitudMecanicoDTO(
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
            )

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
            comentarios=comentarios_dtos,
            pauta_respuestas=pauta_dtos,
        )



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

    async def get_solicitud(self, db: AsyncSession, solicitud_id: int) -> Optional[SolicitudDTO]:
        logger.debug("[MANTENCION] Consultando solicitud | id=%s", solicitud_id)
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def create_solicitud(self, db: AsyncSession, dto: SolicitudCreateDTO, creador_id: int) -> SolicitudDTO:
        logger.info("[MANTENCION] Creando solicitud | n_bus='%s' | creador_id=%s", dto.n_bus, creador_id)
        sol = await mantencion_repository.create_solicitud(db, dto, creador_id)
        logger.info("[MANTENCION] Solicitud creada | id=%s | n_bus='%s' | estado=REPORTADO", sol.id, sol.n_bus)
        return self._to_solicitud_dto(sol)

    async def list_pendientes(self, db: AsyncSession) -> List[SolicitudDTO]:
        logger.debug("[MANTENCION] Listando solicitudes pendientes")
        solicitudes = await mantencion_repository.list_pendientes(db)
        return [self._to_solicitud_dto(s) for s in solicitudes]

    async def list_mis_trabajos(self, db: AsyncSession, mecanico_id: int) -> List[SolicitudDTO]:
        logger.debug("[MANTENCION] Listando trabajos activos | mecanico_id=%s", mecanico_id)
        solicitudes = await mantencion_repository.list_mis_trabajos(db, mecanico_id)
        return [self._to_solicitud_dto(s) for s in solicitudes]

    async def tomar_trabajo(self, db: AsyncSession, solicitud_id: int, lider_id: int, dto: TomarTrabajoDTO) -> SolicitudDTO:
        logger.info("[MANTENCION] Tomar trabajo | solicitud_id=%s | lider_id=%s | colaboradores=%s", solicitud_id, lider_id, dto.colaboradores_ids)
        sol = await mantencion_repository.tomar_trabajo(db, solicitud_id, lider_id, dto)
        logger.info("[MANTENCION] Solicitud en reparación | id=%s | estado=EN_REPARACION", sol.id)
        return self._to_solicitud_dto(sol)

    async def desasignar_mecanico(self, db: AsyncSession, solicitud_id: int, mecanico_id: int, comentario: Optional[str] = None) -> SolicitudDTO:
        logger.info("[MANTENCION] Desasignando mecánico | solicitud_id=%s | mecanico_id=%s", solicitud_id, mecanico_id)
        sol = await mantencion_repository.desasignar_mecanico_individual(db, solicitud_id, mecanico_id, comentario)
        return self._to_solicitud_dto(sol)

    async def liberar_turno(self, db: AsyncSession, solicitud_id: int, usuario_id: int, dto: LiberarTurnoDTO) -> SolicitudDTO:
        logger.info("[MANTENCION] Liberar turno | solicitud_id=%s | usuario_id=%s", solicitud_id, usuario_id)
        sol = await mantencion_repository.liberar_turno(db, solicitud_id, usuario_id, dto)
        return self._to_solicitud_dto(sol)

    async def check_detalle(self, db: AsyncSession, solicitud_id: int, detalle_id: int, mecanico_id: int, resuelto: bool) -> SolicitudDTO:
        logger.info("[MANTENCION] Check detalle | solicitud_id=%s | detalle_id=%s | mecanico_id=%s | resuelto=%s", solicitud_id, detalle_id, mecanico_id, resuelto)
        sol = await mantencion_repository.check_detalle(db, solicitud_id, detalle_id, mecanico_id, resuelto)
        return self._to_solicitud_dto(sol)

    async def agregar_colaborador(self, db: AsyncSession, solicitud_id: int, lider_id: int, dto: AgregarColaboradorDTO) -> SolicitudDTO:
        logger.info("[MANTENCION] Agregando colaborador en caliente | solicitud_id=%s | lider_id=%s", solicitud_id, lider_id)
        sol = await mantencion_repository.agregar_colaborador(db, solicitud_id, lider_id, dto)
        return self._to_solicitud_dto(sol)

    async def agregar_comentario(self, db: AsyncSession, solicitud_id: int, usuario_id: int, dto: ComentarioCreateDTO) -> SolicitudDTO:
        logger.info("[MANTENCION] Agregando comentario | solicitud_id=%s | usuario_id=%s | tipo=%s", solicitud_id, usuario_id, dto.tipo)
        sol = await mantencion_repository.agregar_comentario(db, solicitud_id, usuario_id, dto)
        return self._to_solicitud_dto(sol)

    async def finalizar_solicitud(self, db: AsyncSession, solicitud_id: int, mecanico_cierre_id: int, dto: FinalizarSolicitudDTO) -> SolicitudDTO:
        logger.info("[MANTENCION] Finalizando solicitud | id=%s | mecanico_cierre_id=%s", solicitud_id, mecanico_cierre_id)
        sol = await mantencion_repository.finalizar_solicitud(db, solicitud_id, mecanico_cierre_id, dto)
        logger.info("[MANTENCION] Solicitud FINALIZADA | id=%s | n_bus='%s'", sol.id, sol.n_bus)
        return self._to_solicitud_dto(sol)

    async def list_auditoria(self, db: AsyncSession) -> List[SolicitudDTO]:
        logger.debug("[MANTENCION] Consultando auditoría completa de solicitudes")
        solicitudes = await mantencion_repository.list_auditoria(db)
        return [self._to_solicitud_dto(s) for s in solicitudes]

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
        sol = await mantencion_repository.autoasignar_fallas_mecanico(
            db,
            solicitud_id=solicitud_id,
            detalles_ids=dto.detalles_ids,
            mecanico_id=mecanico_id,
            comentario=dto.comentario,
            colaboradores_ids=dto.colaboradores_ids,
        )
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
        sol = await mantencion_repository.asignar_fallas_supervisora(
            db,
            solicitud_id=solicitud_id,
            mecanico_id=dto.mecanico_id,
            detalles_ids=dto.detalles_ids,
            supervisor_id=supervisor_id,
            comentario=dto.comentario,
        )
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
        sol = await mantencion_repository.terminar_avance(
            db,
            solicitud_id=solicitud_id,
            mecanico_id=mecanico_id,
            detalles_ids=dto.detalles_ids,
            comentario=dto.comentario,
        )
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
        sol = await mantencion_repository.reportar_repuesto(
            db,
            solicitud_id=solicitud_id,
            detalle_id=detalle_id,
            mecanico_id=mecanico_id,
            falta_repuesto=dto.falta_repuesto,
            comentario=dto.comentario,
        )
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
        await mantencion_repository.guardar_respuestas_pauta(
            db,
            solicitud_id=solicitud_id,
            mecanico_id=mecanico_id,
            respuestas=dto.respuestas,
        )
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
        sol = await mantencion_repository.finalizar_solicitud(
            db,
            solicitud_id=solicitud_id,
            mecanico_cierre_id=mecanico_id,
            dto=dto,
        )
        return self._to_solicitud_dto(sol)

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
        sol = await mantencion_repository.agregar_falla_solicitud(
            db,
            solicitud_id=solicitud_id,
            mecanico_id=mecanico_id,
            dto=dto,
        )
        return self._to_solicitud_dto(sol)


mantencion_service = MantencionService()


