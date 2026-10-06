import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.auth.constants import RolUsuario
from app.modules.taller.constants import EstadoSolicitud, EstadoFalla, TipoEventoFalla
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.taller.dtos import (
    AgregarFallaDTO,
    DetalleUpdateDTO,
    MecanicoResumenDTO,
    ReportarRepuestoDTO,
    ResolverFallaSupervisoraDTO,
    SolicitudDTO,
)
from app.modules.taller.repository.taller_repository import (
    TallerRepository,
    taller_repository,
)
from app.modules.taller.utils import describir_detalle_averia
from app.modules.taller.services.mappers import orm_to_solicitud_dto
from app.modules.taller.services.estadias_helper import (
    asegurar_ingreso_taller_y_estadia,
    attach_comentario_safe,
    attach_mecanico_safe,
)
from app.modules.taller.services.bitacora_adjuntos import guardar_adjuntos_bitacora
from app.modules.taller.services.trazabilidad_fallas import registrar_evento_falla

from app.modules.taller.services.trazabilidad_estados import RegistroEstadoOT, registrar_evento_estado

logger = logging.getLogger(__name__)


class AveriasService:
    """
    Servicio de capa de negocio responsable exclusivamente de la gestión granular
    de averías/fallas en una OT: agregado dinámico en caliente, check/uncheck de reparación,
    resolución por supervisora y reporte de falta de repuestos.
    """

    def __init__(self, repository: Optional[TallerRepository] = None) -> None:
        self.repo = repository or taller_repository

    async def agregar_falla(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        dto: AgregarFallaDTO,
    ) -> SolicitudDTO:
        """Permite agregar una avería detectada durante la atención en taller."""
        logger.info(
            "[MANTENCION] Agregando nueva avería | solicitud_id=%s, mecanico_id=%s, autoasignar=%s",
            solicitud_id,
            mecanico_id,
            dto.autoasignar,
        )
        await self.repo.lock_solicitud_estado(db, solicitud_id)
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")
        estado_ot_anterior = solicitud.estado

        if solicitud.estado == "FINALIZADO":
            raise BusinessRuleException(
                "No se pueden agregar fallas a una solicitud que ya ha sido finalizada"
            )

        now = datetime.now(timezone.utc)
        texto = dto.texto_falla
        if not texto and not dto.falla_id:
            raise BusinessRuleException(
                "Debe indicar el nombre o descripción de la avería a agregar"
            )

        falla_id = dto.falla_id
        f_obj = None
        cat_obj = None
        if dto.categoria_id:
            cat_obj = await self.repo.get_categoria_by_id(db, dto.categoria_id)

        if falla_id:
            f_obj = await self.repo.get_falla_by_id(db, falla_id)
        elif dto.categoria_id:
            falla_id = await self.repo.find_falla_activa_by_categoria(
                db, dto.categoria_id
            )
            if falla_id:
                f_obj = await self.repo.get_falla_by_id(db, falla_id)

        if not texto and cat_obj:
            texto = f_obj.nombre if f_obj else f"Avería de {cat_obj.nombre}"

        # 2. Registrar mecánico ejecutor
        u = await self.repo.get_usuario_by_id(db, mecanico_id)
        mec_nombre = u.nombre_completo if u else "Mecánico"

        # 3. Crear nuevo detalle de falla
        nuevo_detalle = TallerSolicitudDetalle(
            solicitud_id=solicitud.id,
            falla_id=falla_id,
            descripcion_personalizada=texto,
            estado=EstadoFalla.PENDIENTE.value,
            motivo_incompleto=None,
            resuelto=False,
            falta_repuesto=False,
            fecha_creacion=now,
            fecha_reporte=now,
            reportado_por_id=mecanico_id,
            asignaciones=[],
        )
        if f_obj:
            nuevo_detalle.falla = f_obj
        self.repo.add_detalle(db, nuevo_detalle)
        await self.repo.flush(db)
        registrar_evento_falla(
            db,
            self.repo,
            detalle_id=nuevo_detalle.id,
            tipo_evento=TipoEventoFalla.REPORTADA.value,
            actor_id=mecanico_id,
            actor_nombre=mec_nombre,
            estado_anterior=None,
            estado_nuevo=EstadoFalla.PENDIENTE.value,
            fecha_evento=now,
            comentario=texto,
        )

        # 4. Asignación / Resolución según rol y DTO
        es_supervisor = False
        u_rol_nom = getattr(getattr(u, "rol_rel", None), "nombre", None) or ""
        if u and u_rol_nom.upper().strip() in [
            RolUsuario.SUPERVISOR.value,
            RolUsuario.ADMIN.value,
        ]:
            es_supervisor = True

        tipo_bitacora = "AVANCE"
        u_resolutor = None
        u_asig = None

        resolutor_id = dto.effective_resolutor_id
        asignado_id = dto.effective_asignado_id

        if es_supervisor and dto.resuelto and resolutor_id:
            u_resolutor = await self.repo.get_usuario_by_id(db, resolutor_id)
            if not u_resolutor or not u_resolutor.is_active:
                raise BusinessRuleException(
                    "El mecánico resolutor indicado no existe o se encuentra inactivo"
                )
            nuevo_detalle.estado = EstadoFalla.RESUELTA.value
            nuevo_detalle.resuelto = True
            nuevo_detalle.mecanico_resolvio_id = resolutor_id
            nuevo_detalle.mecanico_resolvio = u_resolutor
            nuevo_detalle.fecha_resolucion = now
            db.add(nuevo_detalle)
            tipo_bitacora = "RESOLUCION"
        elif es_supervisor and asignado_id:
            u_asig = await self.repo.get_usuario_by_id(db, asignado_id)
            if not u_asig or not u_asig.is_active:
                raise BusinessRuleException(
                    "El mecánico asignado indicado no existe o se encuentra inactivo"
                )
            nueva_asig = TallerAsignacionFalla(
                solicitud_id=solicitud.id,
                detalle_id=nuevo_detalle.id,
                mecanico_id=asignado_id,
                asignado_por_id=mecanico_id,
                origen="SUPERVISOR",
                is_activo=True,
                fecha_asignacion=now,
                resuelto_en_esta_asignacion=False,
            )
            nueva_asig.mecanico = u_asig
            nueva_asig.asignado_por = u
            self.repo.add_asignacion_falla(db, nueva_asig)
            nuevo_detalle.asignaciones.append(nueva_asig)
            if (
                hasattr(solicitud, "asignaciones_fallas")
                and solicitud.asignaciones_fallas is not None
            ):
                solicitud.asignaciones_fallas.append(nueva_asig)

            presencia = await self.repo.get_presencia_activa_individual(
                db, solicitud.id, dto.mecanico_asignado_id
            )
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
                attach_mecanico_safe(solicitud, nueva_presencia)

            if solicitud.estado in [
                EstadoSolicitud.PENDIENTE.value,
                EstadoSolicitud.LIBERADO.value,
                EstadoSolicitud.REPORTADO.value,
            ]:
                solicitud.estado = EstadoSolicitud.EN_REPARACION.value
                await asegurar_ingreso_taller_y_estadia(
                    self.repo, db, solicitud, now
                )
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
                if (
                    hasattr(solicitud, "asignaciones_fallas")
                    and solicitud.asignaciones_fallas is not None
                ):
                    solicitud.asignaciones_fallas.append(nueva_asig)

                presencia = await self.repo.get_presencia_activa_individual(
                    db, solicitud.id, mecanico_id
                )
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
                    attach_mecanico_safe(solicitud, nueva_presencia)

                if solicitud.estado in [
                    EstadoSolicitud.PENDIENTE.value,
                    EstadoSolicitud.LIBERADO.value,
                    EstadoSolicitud.REPORTADO.value,
                ]:
                    solicitud.estado = EstadoSolicitud.EN_REPARACION.value
                    await asegurar_ingreso_taller_y_estadia(
                        self.repo, db, solicitud, now
                    )

        if hasattr(solicitud, "detalles") and solicitud.detalles is not None:
            solicitud.detalles.append(nuevo_detalle)

        # 5. Registrar en bitácora inmutable
        desc_pers = (
            dto.descripcion_personalizada.strip()
            if dto.descripcion_personalizada
            else None
        )
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
        attach_comentario_safe(solicitud, comentario_entry, mec_nombre)
        solicitud.fecha_actualizacion = now
        if nuevo_detalle.resuelto:
            registrar_evento_falla(
                db,
                self.repo,
                detalle_id=nuevo_detalle.id,
                tipo_evento=TipoEventoFalla.RESUELTA.value,
                actor_id=mecanico_id,
                actor_nombre=mec_nombre,
                estado_anterior=EstadoFalla.PENDIENTE.value,
                estado_nuevo=EstadoFalla.RESUELTA.value,
                fecha_evento=now,
                comentario=dto.descripcion_personalizada,
                mecanicos_resolutores=[u_resolutor] if u_resolutor else [],
            )

        await registrar_evento_estado(
            db, RegistroEstadoOT(
                solicitud_id=solicitud.id, estado_anterior=estado_ot_anterior,
                estado_nuevo=solicitud.estado, actor_id=mecanico_id, actor_nombre=mec_nombre,
                fecha_evento=now, comentario=comentario_entry,
                motivo=comentario_entry.comentario,
            ),
        )
        await db.commit()
        return orm_to_solicitud_dto(solicitud)

    async def check_detalle(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        mecanico_id: int,
        resuelto: Optional[bool] = None,
        mecanico_nombre: Optional[str] = None,
        mecanico_resolvio_id: Optional[int] = None,
        estado: Optional[EstadoFalla] = None,
        motivo_incompleto: Optional[str] = None,
        comentario: Optional[str] = None,
        fotos: Optional[List[UploadFile]] = None,
    ) -> DetalleUpdateDTO:
        """Actualiza el estado de una falla (PENDIENTE, INCOMPLETA, RESUELTA) retornando un DTO atómico."""
        target_estado: EstadoFalla
        if estado is not None:
            target_estado = estado
        elif resuelto is not None:
            target_estado = EstadoFalla.RESUELTA if resuelto else EstadoFalla.PENDIENTE
        else:
            target_estado = EstadoFalla.RESUELTA

        logger.info(
            "[MANTENCION] Check detalle atómico | solicitud_id=%s | detalle_id=%s | usuario_id=%s | target_estado=%s | resolutor_id=%s",
            solicitud_id,
            detalle_id,
            mecanico_id,
            target_estado.value,
            mecanico_resolvio_id,
        )
        await self.repo.lock_solicitud_estado(db, solicitud_id)
        detalle_target = await self.repo.get_detalle_operacional(
            db, solicitud_id, detalle_id
        )
        if not detalle_target:
            if not await self.repo.check_solicitud_exists(db, solicitud_id):
                raise NotFoundException("Solicitud de taller no encontrada")
            raise NotFoundException("Detalle de falla no encontrado")

        now = datetime.now(timezone.utc)
        estado_anterior = detalle_target.estado
        is_resuelta = target_estado == EstadoFalla.RESUELTA
        detalle_target.estado = target_estado.value
        detalle_target.resuelto = is_resuelta

        actor_nom = mecanico_nombre or "Mecánico"
        u_mec = None
        if not mecanico_nombre:
            u_mec = await self.repo.get_usuario_by_id(db, mecanico_id)
            if u_mec:
                actor_nom = u_mec.nombre_completo

        falla_nom = describir_detalle_averia(detalle_target)
        resolutor_nom = None

        asigs_activas = await self.repo.get_asignaciones_activas(
            db, solicitud_id=solicitud_id, detalles_ids=[detalle_id]
        )

        mecanicos_resolvieron_dtos: List[MecanicoResumenDTO] = []
        nombres_equipo: List[str] = []
        vistos_ids = set()

        for asig in asigs_activas:
            mec = asig.mecanico
            if mec and mec.id not in vistos_ids:
                vistos_ids.add(mec.id)
                nombres_equipo.append(mec.nombre_completo)
                mecanicos_resolvieron_dtos.append(
                    MecanicoResumenDTO(id=mec.id, nombre=mec.nombre_completo)
                )

        if target_estado == EstadoFalla.RESUELTA:
            for asig in asigs_activas:
                asig.resuelto_en_esta_asignacion = True

            resolutor_id = (
                mecanico_resolvio_id if mecanico_resolvio_id else mecanico_id
            )
            u_resolutor = None
            resolutor_nom = actor_nom
            if resolutor_id and resolutor_id != mecanico_id:
                u_resolutor = await self.repo.get_usuario_by_id(db, resolutor_id)
                if not u_resolutor or not u_resolutor.is_active:
                    raise BusinessRuleException(
                        "El mecánico resolutor indicado no existe o se encuentra inactivo"
                    )
                resolutor_nom = u_resolutor.nombre_completo
            elif u_mec:
                u_resolutor = u_mec

            if resolutor_id and resolutor_id not in vistos_ids and not asigs_activas:
                vistos_ids.add(resolutor_id)
                nombres_equipo.append(resolutor_nom)
                mecanicos_resolvieron_dtos.append(
                    MecanicoResumenDTO(id=resolutor_id, nombre=resolutor_nom)
                )

            detalle_target.mecanico_resolvio_id = resolutor_id
            detalle_target.fecha_resolucion = now
            detalle_target.motivo_incompleto = None
            if u_resolutor:
                detalle_target.mecanico_resolvio = u_resolutor

            if len(nombres_equipo) > 1:
                resolutor_str = ", ".join(nombres_equipo)
                texto_check = f"El equipo [{resolutor_str}] completó la reparación de la falla: '{falla_nom}' (marcado por {actor_nom})"
                resolutor_nom = resolutor_str
            elif len(nombres_equipo) == 1:
                resolutor_nom = nombres_equipo[0]
                if resolutor_id != mecanico_id:
                    texto_check = f"{actor_nom} registró la reparación de la falla '{falla_nom}' por el mecánico {resolutor_nom}"
                else:
                    texto_check = f"{resolutor_nom} completó la reparación de la falla: '{falla_nom}'"
            else:
                texto_check = f"{actor_nom} completó la reparación de la falla: '{falla_nom}'"
                mecanicos_resolvieron_dtos.append(
                    MecanicoResumenDTO(id=mecanico_id, nombre=actor_nom)
                )
            tipo_check = "RESOLUCION"

        elif target_estado == EstadoFalla.INCOMPLETA:
            for asig in asigs_activas:
                asig.resuelto_en_esta_asignacion = False

            detalle_target.mecanico_resolvio_id = None
            detalle_target.mecanico_resolvio = None
            detalle_target.fecha_resolucion = None
            motivo_limpio = (motivo_incompleto or "").strip() or None
            detalle_target.motivo_incompleto = motivo_limpio

            if len(nombres_equipo) > 1:
                texto_check = f"El equipo [{', '.join(nombres_equipo)}] marcó la falla '{falla_nom}' como INCOMPLETA"
                if motivo_limpio:
                    texto_check += f" - Motivo: {motivo_limpio}"
                texto_check += f" (registrado por {actor_nom})"
            else:
                texto_check = f"{actor_nom} marcó la falla '{falla_nom}' como INCOMPLETA"
                if motivo_limpio:
                    texto_check += f" - Motivo: {motivo_limpio}"
            tipo_check = "AVANCE"
            resolutor_nom = None
            mecanicos_resolvieron_dtos = []

        else:  # EstadoFalla.PENDIENTE
            for asig in asigs_activas:
                asig.resuelto_en_esta_asignacion = False

            detalle_target.mecanico_resolvio_id = None
            detalle_target.mecanico_resolvio = None
            detalle_target.fecha_resolucion = None
            detalle_target.motivo_incompleto = None

            if len(nombres_equipo) > 1:
                texto_check = f"El equipo [{', '.join(nombres_equipo)}] reabrió la falla: '{falla_nom}' (registrado por {actor_nom})"
            else:
                texto_check = f"{actor_nom} reabrió la falla: '{falla_nom}'"
            tipo_check = "REAPERTURA"
            resolutor_nom = None
            mecanicos_resolvieron_dtos = []

        observacion = (comentario or "").strip()
        if observacion and not (
            target_estado == EstadoFalla.INCOMPLETA
            and observacion == (detalle_target.motivo_incompleto or "")
        ):
            texto_check += f" - Observación: {observacion}"

        db.add(detalle_target)

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
        await self.repo.touch_fecha_actualizacion(db, solicitud_id, now)
        await guardar_adjuntos_bitacora(
            db,
            comentario=comentario_entry,
            solicitud_id=solicitud_id,
            detalle_id=detalle_id,
            usuario_id=mecanico_id,
            fotos=fotos,
        )
        tipo_evento = {
            EstadoFalla.RESUELTA: TipoEventoFalla.RESUELTA.value,
            EstadoFalla.INCOMPLETA: TipoEventoFalla.INCOMPLETA.value,
            EstadoFalla.PENDIENTE: TipoEventoFalla.REABIERTA.value,
        }[target_estado]
        registrar_evento_falla(
            db,
            self.repo,
            detalle_id=detalle_target.id,
            tipo_evento=tipo_evento,
            actor_id=mecanico_id,
            actor_nombre=actor_nom,
            estado_anterior=estado_anterior,
            estado_nuevo=detalle_target.estado,
            fecha_evento=now,
            comentario=observacion or detalle_target.motivo_incompleto,
            mecanicos_resolutores=mecanicos_resolvieron_dtos if is_resuelta else [],
        )

        await db.commit()
        return DetalleUpdateDTO(
            detalle_id=detalle_target.id,
            solicitud_id=solicitud_id,
            estado=detalle_target.estado,
            motivo_incompleto=detalle_target.motivo_incompleto,
            resuelto=detalle_target.resuelto,
            falta_repuesto=getattr(detalle_target, "falta_repuesto", False),
            mecanico_resolvio_id=detalle_target.mecanico_resolvio_id,
            mecanico_resolvio_nombre=resolutor_nom if is_resuelta else None,
            mecanicos_resolvieron=mecanicos_resolvieron_dtos if is_resuelta else [],
            comentario_repuesto=getattr(detalle_target, "comentario_repuesto", None),
            fecha_resolucion=detalle_target.fecha_resolucion,
        )

    async def reportar_repuesto(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        dto: ReportarRepuestoDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> DetalleUpdateDTO:
        """Reporta si una falla no puede continuar por falta de repuestos."""
        logger.info(
            "[MANTENCION] Reportando repuesto atómico | solicitud_id=%s, detalle_id=%s, falta=%s",
            solicitud_id,
            detalle_id,
            dto.falta_repuesto,
        )
        await self.repo.lock_solicitud_estado(db, solicitud_id)
        detalle = await self.repo.get_detalle_operacional(db, solicitud_id, detalle_id)
        if not detalle:
            if not await self.repo.check_solicitud_exists(db, solicitud_id):
                raise NotFoundException("Solicitud de taller no encontrada")
            raise NotFoundException(
                f"Detalle con ID {detalle_id} no encontrado en la solicitud"
            )

        if dto.falta_repuesto and getattr(detalle, "resuelto", False):
            raise BusinessRuleException(
                "No se puede reportar falta de repuesto en una falla que ya fue marcada como resuelta. "
                "Si la falla requiere nueva intervención, desmarque primero su resolución."
            )

        detalle.falta_repuesto = dto.falta_repuesto
        detalle.comentario_repuesto = (
            dto.comentario.strip() if dto.comentario else None
        )

        now = datetime.now(timezone.utc)
        tipo_accion = (
            "FALTA_REPUESTO" if dto.falta_repuesto else "REPUESTO_DISPONIBLE"
        )

        if not mecanico_nombre:
            u_mec = await self.repo.get_usuario_by_id(db, mecanico_id)
            mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"
        else:
            u_mec = None
            mec_nom = mecanico_nombre

        falla_nom = describir_detalle_averia(detalle)
        estado_str = (
            "FALTA DE REPUESTO" if dto.falta_repuesto else "REPUESTO DISPONIBLE"
        )

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
        await self.repo.touch_fecha_actualizacion(db, solicitud_id, now)
        registrar_evento_falla(
            db,
            self.repo,
            detalle_id=detalle.id,
            tipo_evento=(
                TipoEventoFalla.FALTA_REPUESTO_ACTIVADA.value
                if dto.falta_repuesto
                else TipoEventoFalla.FALTA_REPUESTO_RETIRADA.value
            ),
            actor_id=mecanico_id,
            actor_nombre=mec_nom,
            estado_anterior=detalle.estado,
            estado_nuevo=detalle.estado,
            fecha_evento=now,
            comentario=detalle.comentario_repuesto,
        )

        await db.commit()
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

    async def resolver_falla_supervisora(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        dto: ResolverFallaSupervisoraDTO,
        supervisor_id: int,
        supervisor_nombre: Optional[str] = None,
        fotos: Optional[List[UploadFile]] = None,
    ) -> DetalleUpdateDTO:
        """Permite a la supervisora marcar una falla como resuelta indicando qué mecánico la arregló."""
        logger.info(
            "[MANTENCION] Supervisora gestionando resolución de falla | solicitud_id=%s | detalle_id=%s | supervisor_id=%s | resuelto=%s | mecanico_id=%s",
            solicitud_id,
            detalle_id,
            supervisor_id,
            dto.resuelto,
            dto.mecanico_id,
        )
        await self.repo.lock_solicitud_estado(db, solicitud_id)
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if solicitud.estado == EstadoSolicitud.FINALIZADO.value:
            raise BusinessRuleException(
                "No se pueden modificar fallas de una solicitud que ya ha sido finalizada"
            )

        detalle_target = None
        if hasattr(solicitud, "detalles") and solicitud.detalles:
            for det in solicitud.detalles:
                if det.id == detalle_id:
                    detalle_target = det
                    break

        if not detalle_target:
            detalle_target = await self.repo.get_detalle_operacional(
                db, solicitud_id, detalle_id
            )

        if not detalle_target:
            raise NotFoundException(
                "Detalle de falla no encontrado en la orden de taller"
            )

        now = datetime.now(timezone.utc)
        estado_anterior = detalle_target.estado
        falla_nom = describir_detalle_averia(detalle_target)

        sup_nom = supervisor_nombre
        if not sup_nom:
            u_sup = await self.repo.get_usuario_by_id(db, supervisor_id)
            sup_nom = u_sup.nombre_completo if u_sup else "Supervisora"

        target_estado = dto.effective_estado
        is_resuelta = target_estado == EstadoFalla.RESUELTA
        detalle_target.estado = target_estado.value
        detalle_target.resuelto = is_resuelta

        mec_nom = None

        asigs_activas = await self.repo.get_asignaciones_activas(
            db, solicitud_id=solicitud_id, detalles_ids=[detalle_id]
        )

        mecanicos_resolvieron_dtos: List[MecanicoResumenDTO] = []
        nombres_equipo: List[str] = []
        vistos_ids = set()

        for asig in asigs_activas:
            mec = asig.mecanico
            if mec and mec.id not in vistos_ids:
                vistos_ids.add(mec.id)
                nombres_equipo.append(mec.nombre_completo)
                mecanicos_resolvieron_dtos.append(
                    MecanicoResumenDTO(id=mec.id, nombre=mec.nombre_completo)
                )

        if target_estado == EstadoFalla.RESUELTA:
            mecs_ids_dto = dto.effective_mecanicos_ids
            if not mecs_ids_dto and not asigs_activas:
                raise BusinessRuleException(
                    "Debe indicar al menos un mecánico que realizó la reparación de la avería"
                )

            # Validar y registrar cada mecánico seleccionado por el supervisor
            primer_mec_obj = None
            ids_asig_activa = {asig.mecanico_id for asig in asigs_activas}

            for mec_id_item in mecs_ids_dto:
                u_mec_item = await self.repo.get_usuario_by_id(db, mec_id_item)
                if not u_mec_item or not u_mec_item.is_active:
                    raise BusinessRuleException(
                        f"El mecánico con ID {mec_id_item} no existe o no se encuentra activo en el sistema"
                    )
                if mec_id_item not in vistos_ids:
                    vistos_ids.add(mec_id_item)
                    nombres_equipo.append(u_mec_item.nombre_completo)
                    mecanicos_resolvieron_dtos.append(
                        MecanicoResumenDTO(id=mec_id_item, nombre=u_mec_item.nombre_completo)
                    )
                if primer_mec_obj is None:
                    primer_mec_obj = u_mec_item

                # Crear asignación si el mecánico seleccionado no tenía una activa
                if mec_id_item not in ids_asig_activa:
                    nueva_asig = TallerAsignacionFalla(
                        solicitud_id=solicitud_id,
                        detalle_id=detalle_id,
                        mecanico_id=mec_id_item,
                        asignado_por_id=supervisor_id,
                        origen="SUPERVISOR",
                        is_activo=True,
                        fecha_asignacion=now,
                        resuelto_en_esta_asignacion=True,
                    )
                    nueva_asig.mecanico = u_mec_item
                    self.repo.add_asignacion_falla(db, nueva_asig)
                    ids_asig_activa.add(mec_id_item)

            # Marcar TODAS las asignaciones activas previas como resueltas
            for asig in asigs_activas:
                asig.resuelto_en_esta_asignacion = True

            # El campo singular apunta al primer mecánico del DTO (o al primero de la cuadrilla)
            resolutor_id_principal = (
                mecs_ids_dto[0] if mecs_ids_dto
                else (asigs_activas[0].mecanico_id if asigs_activas else None)
            )
            detalle_target.mecanico_resolvio_id = resolutor_id_principal
            detalle_target.fecha_resolucion = now
            detalle_target.motivo_incompleto = None
            if primer_mec_obj and resolutor_id_principal == primer_mec_obj.id:
                detalle_target.mecanico_resolvio = primer_mec_obj
            db.add(detalle_target)

            if len(nombres_equipo) > 1:
                mec_nom = ", ".join(nombres_equipo)
                texto_check = f"Supervisora {sup_nom} registró la reparación de la falla '{falla_nom}' por el equipo [{mec_nom}]"
            elif len(nombres_equipo) == 1:
                mec_nom = nombres_equipo[0]
                texto_check = f"Supervisora {sup_nom} registró la reparación de la falla '{falla_nom}' por el mecánico {mec_nom}"
            else:
                mec_nom = "Mecánico"
                texto_check = f"Supervisora {sup_nom} registró la reparación de la falla '{falla_nom}'"

            if dto.comentario and dto.comentario.strip():
                texto_check += f" - Observación: {dto.comentario.strip()}"
            tipo_check = "RESOLUCION"

        elif target_estado == EstadoFalla.INCOMPLETA:
            for asig in asigs_activas:
                asig.resuelto_en_esta_asignacion = False

            detalle_target.mecanico_resolvio_id = None
            detalle_target.mecanico_resolvio = None
            detalle_target.fecha_resolucion = None
            motivo_limpio = (dto.motivo_incompleto or dto.comentario or "").strip() or None
            detalle_target.motivo_incompleto = motivo_limpio
            db.add(detalle_target)

            if len(nombres_equipo) > 1:
                texto_check = f"Supervisora {sup_nom} marcó la falla '{falla_nom}' del equipo [{', '.join(nombres_equipo)}] como INCOMPLETA"
            else:
                texto_check = f"Supervisora {sup_nom} marcó la falla '{falla_nom}' como INCOMPLETA"
            if motivo_limpio:
                texto_check += f" - Motivo: {motivo_limpio}"
            tipo_check = "AVANCE"
            mec_nom = None
            mecanicos_resolvieron_dtos = []

        else:  # EstadoFalla.PENDIENTE
            for asig in asigs_activas:
                asig.resuelto_en_esta_asignacion = False

            detalle_target.mecanico_resolvio_id = None
            detalle_target.mecanico_resolvio = None
            detalle_target.fecha_resolucion = None
            detalle_target.motivo_incompleto = None
            db.add(detalle_target)

            texto_check = f"Supervisora {sup_nom} reabrió la falla '{falla_nom}' (estado PENDIENTE)"
            if dto.comentario and dto.comentario.strip():
                texto_check += f" - Observación: {dto.comentario.strip()}"
            tipo_check = "REAPERTURA"
            mec_nom = None
            mecanicos_resolvieron_dtos = []

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud_id,
            usuario_id=supervisor_id,
            tipo=tipo_check,
            comentario=texto_check,
            fecha_registro=now,
        )
        self.repo.add_comentario(db, comentario_entry)
        await self.repo.touch_fecha_actualizacion(db, solicitud_id, now)
        await guardar_adjuntos_bitacora(
            db,
            comentario=comentario_entry,
            solicitud_id=solicitud_id,
            detalle_id=detalle_id,
            usuario_id=supervisor_id,
            fotos=fotos,
        )
        tipo_evento = {
            EstadoFalla.RESUELTA: TipoEventoFalla.RESUELTA.value,
            EstadoFalla.INCOMPLETA: TipoEventoFalla.INCOMPLETA.value,
            EstadoFalla.PENDIENTE: TipoEventoFalla.REABIERTA.value,
        }[target_estado]
        registrar_evento_falla(
            db,
            self.repo,
            detalle_id=detalle_target.id,
            tipo_evento=tipo_evento,
            actor_id=supervisor_id,
            actor_nombre=sup_nom,
            estado_anterior=estado_anterior,
            estado_nuevo=detalle_target.estado,
            fecha_evento=now,
            comentario=dto.comentario or detalle_target.motivo_incompleto,
            mecanicos_resolutores=mecanicos_resolvieron_dtos if is_resuelta else [],
        )

        await db.commit()
        return DetalleUpdateDTO(
            detalle_id=detalle_target.id,
            solicitud_id=solicitud_id,
            estado=detalle_target.estado,
            motivo_incompleto=detalle_target.motivo_incompleto,
            resuelto=detalle_target.resuelto,
            falta_repuesto=getattr(detalle_target, "falta_repuesto", False),
            mecanico_resolvio_id=detalle_target.mecanico_resolvio_id,
            mecanico_resolvio_nombre=mec_nom if is_resuelta else None,
            mecanicos_resolvieron=mecanicos_resolvieron_dtos if is_resuelta else [],
            comentario_repuesto=getattr(detalle_target, "comentario_repuesto", None),
            fecha_resolucion=detalle_target.fecha_resolucion,
        )


averias_service = AveriasService()
