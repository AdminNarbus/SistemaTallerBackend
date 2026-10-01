import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.auth.constants import RolUsuario
from app.modules.taller.constants import EstadoSolicitud
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.taller.dtos import (
    AgregarFallaDTO,
    DetalleUpdateDTO,
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
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if solicitud.estado == "FINALIZADO":
            raise BusinessRuleException(
                "No se pueden agregar fallas a una solicitud que ya ha sido finalizada"
            )

        now = datetime.now()
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
                origen="SUPERVISION",
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

        await db.commit()
        return orm_to_solicitud_dto(solicitud)

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
        """Marca o desmarca un check de falla resuelta retornando un DTO atómico."""
        logger.info(
            "[MANTENCION] Check detalle atómico | solicitud_id=%s | detalle_id=%s | usuario_id=%s | resuelto=%s | mecanico_resolvio_id=%s",
            solicitud_id,
            detalle_id,
            mecanico_id,
            resuelto,
            mecanico_resolvio_id,
        )
        detalle_target = await self.repo.get_detalle_operacional(
            db, solicitud_id, detalle_id
        )
        if not detalle_target:
            if not await self.repo.check_solicitud_exists(db, solicitud_id):
                raise NotFoundException("Solicitud de taller no encontrada")
            raise NotFoundException("Detalle de falla no encontrado")

        now = datetime.now()
        detalle_target.resuelto = resuelto

        resolutor_id = (
            mecanico_resolvio_id
            if (mecanico_resolvio_id and resuelto)
            else (mecanico_id if resuelto else None)
        )

        actor_nom = mecanico_nombre or "Mecánico"
        u_mec = None
        if not mecanico_nombre:
            u_mec = await self.repo.get_usuario_by_id(db, mecanico_id)
            if u_mec:
                actor_nom = u_mec.nombre_completo

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

        falla_nom = describir_detalle_averia(detalle_target)

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
        await self.repo.touch_fecha_actualizacion(db, solicitud_id, now)

        await db.commit()
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

        now = datetime.now()
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

        now = datetime.now()
        falla_nom = describir_detalle_averia(detalle_target)

        sup_nom = supervisor_nombre
        if not sup_nom:
            u_sup = await self.repo.get_usuario_by_id(db, supervisor_id)
            sup_nom = u_sup.nombre_completo if u_sup else "Supervisora"

        mec_nom = None
        mec_id = dto.effective_mecanico_id

        if dto.resuelto:
            if not mec_id:
                raise BusinessRuleException(
                    "Debe indicar el ID del mecánico que realizó la reparación de la avería"
                )

            u_mec = await self.repo.get_usuario_by_id(db, mec_id)
            if not u_mec or not u_mec.is_active:
                raise BusinessRuleException(
                    "El mecánico indicado no existe o no se encuentra activo en el sistema"
                )

            mec_nom = u_mec.nombre_completo
            detalle_target.resuelto = True
            detalle_target.mecanico_resolvio_id = mec_id
            detalle_target.mecanico_resolvio = u_mec
            detalle_target.fecha_resolucion = now
            db.add(detalle_target)

            if (
                hasattr(detalle_target, "asignaciones")
                and detalle_target.asignaciones
            ):
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
        await self.repo.touch_fecha_actualizacion(db, solicitud_id, now)

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


averias_service = AveriasService()
