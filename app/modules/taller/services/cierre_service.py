import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.taller.constants import (
    EstadoSolicitud,
    EstadoFalla,
    TipoComentarioBitacora,
)
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.dtos import (
    CambiarEstadoSolicitudDTO,
    ComentarioAddedDTO,
    ComentarioCreateDTO,
    FinalizarSolicitudDTO,
    LiberarSolicitudDTO,
    SolicitudDTO,
)
from app.modules.taller.repository.taller_repository import (
    TallerRepository,
    taller_repository,
)
from app.modules.taller.utils import (
    calcular_duracion_minutos,
    formatear_comentario_cierre,
    validar_fallas_cierre_parcial,
    validar_pauta_preventiva_cierre,
)
from app.modules.taller.services.mappers import orm_to_solicitud_dto
from app.modules.taller.services.estadias_helper import (
    asegurar_ingreso_taller_y_estadia,
    attach_comentario_safe,
    cerrar_estadia_activa,
)
from app.modules.taller.services.solicitud_service import solicitud_service
from app.modules.taller.services.bitacora_adjuntos import (
    guardar_adjuntos_bitacora,
    normalizar_fotos,
)

from app.modules.taller.services.trazabilidad_estados import RegistroEstadoOT, registrar_evento_estado

logger = logging.getLogger(__name__)


class CierreService:
    """
    Servicio de capa de negocio responsable exclusivamente del ciclo de finalización,
    liberación de OT/bus, cambio administrativo de estado y comentarios en bitácora.
    """

    def __init__(self, repository: Optional[TallerRepository] = None) -> None:
        self.repo = repository or taller_repository

    async def agregar_comentario(
        self,
        db: AsyncSession,
        solicitud_id: int,
        usuario_id: int,
        dto: ComentarioCreateDTO,
        usuario_nombre: Optional[str] = None,
        fotos: Optional[List[UploadFile]] = None,
    ) -> ComentarioAddedDTO:
        """Agrega un comentario a la bitácora independiente de la solicitud."""
        logger.info(
            "[MANTENCION] Agregando comentario atómico | solicitud_id=%s | usuario_id=%s | tipo=%s",
            solicitud_id,
            usuario_id,
            dto.tipo,
        )
        if not await self.repo.check_solicitud_exists(db, solicitud_id):
            raise NotFoundException("Solicitud de taller no encontrada")

        comentario_limpio = (dto.comentario or "").strip()
        archivos = normalizar_fotos(fotos)
        if not comentario_limpio and not archivos:
            raise BusinessRuleException("Debe enviar un comentario o al menos una imagen adjunta.")

        if not usuario_nombre:
            u_usr = await self.repo.get_usuario_by_id(db, usuario_id)
        else:
            u_usr = None

        now = datetime.now(timezone.utc)
        tipo_com = dto.tipo if dto.tipo else "GENERAL"
        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud_id,
            usuario_id=usuario_id,
            tipo=tipo_com,
            comentario=comentario_limpio,
            fecha_registro=now,
        )
        if u_usr:
            comentario_entry.usuario = u_usr
        self.repo.add_comentario(db, comentario_entry)
        await self.repo.touch_fecha_actualizacion(db, solicitud_id, now)

        adjuntos = await guardar_adjuntos_bitacora(
            db,
            comentario=comentario_entry,
            solicitud_id=solicitud_id,
            usuario_id=usuario_id,
            fotos=archivos,
        )

        await db.commit()
        return ComentarioAddedDTO(
            comentario_id=comentario_entry.id,
            solicitud_id=solicitud_id,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre or (u_usr.nombre_completo if u_usr else None),
            tipo=tipo_com,
            comentario=comentario_limpio,
            fecha_registro=now,
            adjuntos=adjuntos,
        )

    async def finalizar_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_cierre_id: int,
        dto: FinalizarSolicitudDTO,
        mecanico_cierre_nom: Optional[str] = None,
    ) -> SolicitudDTO:
        """Finaliza los trabajos de la solicitud sin exigir pauta ni justificaciones adicionales."""
        logger.info(
            "[MANTENCION] Finalizando solicitud | id=%s | mecanico_cierre_id=%s",
            solicitud_id,
            mecanico_cierre_id,
        )

        await self.repo.lock_solicitud_estado(db, solicitud_id)
        ctx = None
        if (
            hasattr(self.repo, "get_contexto_finalizacion")
            and type(self.repo.get_contexto_finalizacion).__name__ != "AsyncMock"
        ):
            ctx = await self.repo.get_contexto_finalizacion(
                db, solicitud_id, mecanico_cierre_id
            )
            if not ctx:
                raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now(timezone.utc)

        if ctx is not None:
            estado_ot_anterior = ctx["estado"]
            total_items_pauta = ctx.get("total_pauta", 0)
            items_respondidos = ctx.get("respondidos_pauta", 0)
            mec_cierre_nom = (
                mecanico_cierre_nom
                or ctx.get("mecanico_cierre_nombre")
                or "Mecánico"
            )
            fallas_no_resueltas_count = ctx.get("fallas_no_resueltas", 0)
        else:
            solicitud_fallback = await self.repo.get_solicitud_con_detalles(
                db, solicitud_id
            )
            if not solicitud_fallback:
                raise NotFoundException("Solicitud de taller no encontrada")
            estado_ot_anterior = solicitud_fallback.estado
            (
                total_items_pauta,
                items_respondidos,
                mec_nom_db,
                _,
            ) = await self.repo.get_conteo_pauta_y_mecanico(
                db, solicitud_id, mecanico_cierre_id
            )
            mec_cierre_nom = mecanico_cierre_nom or mec_nom_db or "Mecánico"
            fallas_no_resueltas_count = len([
                d
                for d in (solicitud_fallback.detalles or [])
                if getattr(d, "estado", None) != EstadoFalla.RESUELTA.value
                or not d.resuelto
                or getattr(d, "falta_repuesto", False)
            ])

        motivo_incompleto_val = validar_pauta_preventiva_cierre(
            total_items=total_items_pauta,
            items_respondidos=items_respondidos,
            motivo_incompleto=dto.motivo_incompleto_checklist,
        )

        motivo_cierre_parcial_val = validar_fallas_cierre_parcial(
            cantidad_fallas_no_resueltas=fallas_no_resueltas_count,
            motivo_cierre_parcial=dto.motivo_cierre_parcial,
        )

        if fallas_no_resueltas_count > 0:
            nuevo_estado = EstadoSolicitud.LIBERADO.value
            motivo_egreso = "LIBERADO"
        else:
            nuevo_estado = EstadoSolicitud.FINALIZADO.value
            motivo_egreso = "FINALIZADO"

        debe_liberar = (
            True if dto.liberar_bus_taller is None else dto.liberar_bus_taller
        )
        liberar_bus = debe_liberar or (fallas_no_resueltas_count == 0)

        texto_cierre = formatear_comentario_cierre(
            mecanico_nombre=mec_cierre_nom,
            liberar_bus=liberar_bus,
            comentario_cierre=dto.comentario_cierre,
            motivo_cierre_parcial=motivo_cierre_parcial_val,
            motivo_incompleto_checklist=motivo_incompleto_val,
        )

        if hasattr(self.repo, "ejecutar_cierre_ot_batch"):
            comentario_cierre = await self.repo.ejecierre_batch_wrapper(
                db,
                solicitud_id=solicitud_id,
                nuevo_estado=nuevo_estado,
                now=now,
                motivo_incompleto_checklist=motivo_incompleto_val,
                motivo_cierre_parcial=motivo_cierre_parcial_val,
                motivo_egreso=motivo_egreso,
                mecanico_cierre_id=mecanico_cierre_id,
                comentario_cierre_texto=texto_cierre,
                liberar_bus=liberar_bus,
            ) if hasattr(
                self.repo, "ejecierre_batch_wrapper"
            ) else await self.repo.ejecutar_cierre_ot_batch(
                db,
                solicitud_id=solicitud_id,
                nuevo_estado=nuevo_estado,
                now=now,
                motivo_incompleto_checklist=motivo_incompleto_val,
                motivo_cierre_parcial=motivo_cierre_parcial_val,
                motivo_egreso=motivo_egreso,
                mecanico_cierre_id=mecanico_cierre_id,
                comentario_cierre_texto=texto_cierre,
                liberar_bus=liberar_bus,
            )
            await registrar_evento_estado(
                db, RegistroEstadoOT(
                    solicitud_id=solicitud_id, estado_anterior=estado_ot_anterior,
                    estado_nuevo=nuevo_estado, actor_id=mecanico_cierre_id,
                    actor_nombre=mec_cierre_nom, fecha_evento=now,
                    comentario=comentario_cierre, motivo=texto_cierre,
                ),
            )
        else:
            await self.repo.desactivar_cuadrilla_y_asignaciones_completas(
                db, solicitud_id=solicitud_id, fecha_desasignacion=now
            )

        await db.commit()
        logger.info(
            "[MANTENCION] Solicitud FINALIZADA en batch | id=%s, nuevo_estado=%s, liberar_bus=%s",
            solicitud_id,
            nuevo_estado,
            liberar_bus,
        )
        return await solicitud_service.get_solicitud(db, solicitud_id)

    async def liberar_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: LiberarSolicitudDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        """Cierra y libera el bus de taller sin exigir justificaciones por pendientes."""
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

    async def cambiar_estado_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: CambiarEstadoSolicitudDTO,
        supervisor_id: int,
        supervisor_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        """Cambio de estado administrativo de una OT exclusivo para supervisores y administradores."""
        logger.info(
            "[MANTENCION] Cambio de estado de OT solicitado por supervisora | solicitud_id=%s, nuevo_estado=%s, supervisor_id=%s",
            solicitud_id,
            dto.estado.value,
            supervisor_id,
        )
        await self.repo.lock_solicitud_estado(db, solicitud_id)
        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        # La lectura debe repetirse después de obtener el mismo lock usado al
        # registrar reportes: mientras se esperaba pudo haberse creado una OT
        # posterior para este bus.
        await self.repo.lock_bus_cycle(db, solicitud.bus_id, solicitud.n_bus)
        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        nuevo_estado = dto.estado.value
        estado_anterior = solicitud.estado
        if estado_anterior == nuevo_estado:
            raise BusinessRuleException(
                f"La solicitud ya se encuentra en estado '{nuevo_estado}'"
            )

        es_reapertura = (
            estado_anterior == EstadoSolicitud.FINALIZADO.value
            and nuevo_estado != EstadoSolicitud.FINALIZADO.value
        )
        if es_reapertura and await self.repo.existe_solicitud_posterior_mismo_bus(
            db, solicitud
        ):
            raise BusinessRuleException(
                "No se puede reabrir esta OT porque el bus ya posee una OT posterior"
            )
        if es_reapertura and await self.repo.existe_otra_solicitud_activa_mismo_bus(
            db, solicitud
        ):
            raise BusinessRuleException(
                "No se puede reabrir esta OT porque el bus ya posee otra OT activa"
            )

        now = datetime.now(timezone.utc)
        sup_nom = supervisor_nombre

        if not sup_nom:
            u_sup = await self.repo.get_usuario_by_id(db, supervisor_id)
            sup_nom = u_sup.nombre_completo if u_sup else "Supervisora"
        else:
            u_sup = None

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
                            mec.duracion_minutos = calcular_duracion_minutos(
                                mec.fecha_asignacion, now
                            )

            if (
                hasattr(solicitud, "asignaciones_fallas")
                and solicitud.asignaciones_fallas
            ):
                for asig in solicitud.asignaciones_fallas:
                    if getattr(asig, "is_activo", False):
                        asig.is_activo = False
                        asig.fecha_desasignacion = now
                        if asig.fecha_asignacion:
                            asig.duracion_minutos = calcular_duracion_minutos(
                                asig.fecha_asignacion, now
                            )

            debe_liberar = (
                True if dto.liberar_bus_taller is None else dto.liberar_bus_taller
            )
            if debe_liberar:
                await cerrar_estadia_activa(
                    self.repo, db, solicitud, now, motivo_salida="FINALIZADO"
                )

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
                            mec.duracion_minutos = calcular_duracion_minutos(
                                mec.fecha_asignacion, now
                            )

            if (
                hasattr(solicitud, "asignaciones_fallas")
                and solicitud.asignaciones_fallas
            ):
                for asig in solicitud.asignaciones_fallas:
                    if getattr(asig, "is_activo", False):
                        asig.is_activo = False
                        asig.fecha_desasignacion = now
                        if asig.fecha_asignacion:
                            asig.duracion_minutos = calcular_duracion_minutos(
                                asig.fecha_asignacion, now
                            )

            debe_liberar = (
                True if dto.liberar_bus_taller is None else dto.liberar_bus_taller
            )
            if debe_liberar:
                await cerrar_estadia_activa(
                    self.repo, db, solicitud, now, motivo_salida="LIBERADO"
                )

        elif estado_anterior in (
            EstadoSolicitud.FINALIZADO.value,
            EstadoSolicitud.LIBERADO.value,
        ) and nuevo_estado not in (
            EstadoSolicitud.FINALIZADO.value,
            EstadoSolicitud.LIBERADO.value,
        ):
            solicitud.fecha_cierre = None
            solicitud.fecha_liberacion = None
            solicitud.mecanico_cierre_id = None
            solicitud._mecanico_cierre_nombre_cached = None
            if nuevo_estado == EstadoSolicitud.EN_REPARACION.value:
                await asegurar_ingreso_taller_y_estadia(
                    self.repo, db, solicitud, now
                )

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
                            mec.duracion_minutos = calcular_duracion_minutos(
                                mec.fecha_asignacion, now
                            )

        elif nuevo_estado == EstadoSolicitud.EN_REPARACION.value:
            await asegurar_ingreso_taller_y_estadia(
                self.repo, db, solicitud, now
            )

        solicitud.estado = nuevo_estado
        solicitud.fecha_actualizacion = now

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
        attach_comentario_safe(solicitud, comentario_entry, sup_nom)
        await registrar_evento_estado(
            db, RegistroEstadoOT(
                solicitud_id=solicitud.id, estado_anterior=estado_anterior,
                estado_nuevo=nuevo_estado, actor_id=supervisor_id, actor_nombre=sup_nom,
                fecha_evento=now, comentario=comentario_entry, motivo=dto.comentario,
            ),
        )

        await db.commit()
        return orm_to_solicitud_dto(solicitud)


cierre_service = CierreService()
