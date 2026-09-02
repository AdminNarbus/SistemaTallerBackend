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
            if det.falla:
                cat_dto = None
                if det.falla.categoria:
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

            mec_resolvio_nombre = None
            if det.mecanico_resolvio:
                mec_resolvio_nombre = f"{det.mecanico_resolvio.nombre or ''} {det.mecanico_resolvio.apellido or ''}".strip() or det.mecanico_resolvio.username

            mecanicos_asignados = []
            historial_asignaciones = []
            if hasattr(det, "asignaciones") and det.asignaciones:
                for asig in det.asignaciones:
                    mec_nom = None
                    if asig.mecanico:
                        mec_nom = f"{asig.mecanico.nombre or ''} {asig.mecanico.apellido or ''}".strip() or asig.mecanico.username
                    asig_por_nom = None
                    if asig.asignado_por:
                        asig_por_nom = f"{asig.asignado_por.nombre or ''} {asig.asignado_por.apellido or ''}".strip() or asig.asignado_por.username

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
            mec_nombre = None
            if mec.mecanico:
                mec_nombre = f"{mec.mecanico.nombre or ''} {mec.mecanico.apellido or ''}".strip() or mec.mecanico.username

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
            usr_nombre = None
            if com.usuario:
                usr_nombre = f"{com.usuario.nombre or ''} {com.usuario.apellido or ''}".strip() or com.usuario.username

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

        creador_nombre = None
        if sol.creador:
            creador_nombre = f"{sol.creador.nombre or ''} {sol.creador.apellido or ''}".strip() or sol.creador.username

        mecanico_cierre_nombre = None
        if sol.mecanico_cierre:
            mecanico_cierre_nombre = f"{sol.mecanico_cierre.nombre or ''} {sol.mecanico_cierre.apellido or ''}".strip() or sol.mecanico_cierre.username

        bus_patente = sol.bus.patente if sol.bus else None

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
            detalles=detalles_dtos,
            mecanicos=mecanicos_dtos,
            comentarios=comentarios_dtos,
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
            "[MANTENCION] Autoasignando fallas atómicas | solicitud_id=%s, mecanico_id=%s, fallas=%s",
            solicitud_id,
            mecanico_id,
            dto.detalles_ids,
        )
        sol = await mantencion_repository.autoasignar_fallas_mecanico(
            db,
            solicitud_id=solicitud_id,
            detalles_ids=dto.detalles_ids,
            mecanico_id=mecanico_id,
            comentario=dto.comentario,
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


mantencion_service = MantencionService()

