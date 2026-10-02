import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.taller.constants import EstadoSolicitud
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.taller.dtos import (
    AgregarColaboradorDTO,
    AsignarFallasSupervisoraDTO,
    AutoasignarFallasDTO,
    LiberarTurnoDTO,
    SolicitudDTO,
    TerminarAvanceDTO,
    TomarTrabajoDTO,
)
from app.modules.taller.repository.taller_repository import (
    TallerRepository,
    taller_repository,
)
from app.modules.taller.utils import (
    calcular_duracion_minutos,
    describir_detalle_averia,
)
from app.modules.taller.services.mappers import orm_to_solicitud_dto
from app.modules.taller.services.estadias_helper import (
    asegurar_ingreso_taller_y_estadia,
    attach_comentario_safe,
    attach_mecanico_safe,
)

logger = logging.getLogger(__name__)


class CuadrillaService:
    """
    Servicio de capa de negocio responsable exclusivamente de la gestión de cuadrillas,
    asignaciones colaborativas de fallas, presencia de mecánicos y término de turnos/avances.
    """

    def __init__(self, repository: Optional[TallerRepository] = None) -> None:
        self.repo = repository or taller_repository

    async def tomar_trabajo(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        dto: TomarTrabajoDTO,
    ) -> SolicitudDTO:
        """Auto-asignación de bus + invitación a colaboradores + comentario inicial opcional."""
        logger.info(
            "[MANTENCION] Tomar trabajo | solicitud_id=%s | mecanico_id=%s | colaboradores=%s",
            solicitud_id,
            mecanico_id,
            dto.colaboradores_ids,
        )
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        # 1. Desactivar mecánicos previos
        await self.repo.desactivar_mecanicos_activos(
            db, solicitud_id=solicitud.id, fecha_desasignacion=now
        )
        if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
            for m in solicitud.mecanicos:
                if getattr(m, "is_activo", False):
                    m.is_activo = False
                    m.fecha_desasignacion = now

        # 2. Resolución batch de usuarios
        from app.modules.auth.repository.user_repository import user_repository

        target_colab_ids = set(dto.colaboradores_ids or [])
        if dto.colaboradores_nombres:
            colab_users = await user_repository.get_mecanicos_by_nombres_o_usernames(
                db, dto.colaboradores_nombres
            )
            for u in colab_users:
                target_colab_ids.add(u.id)

        all_user_ids = [mecanico_id] + [cid for cid in target_colab_ids if cid != mecanico_id]
        users_map = await user_repository.get_by_ids_map(db, all_user_ids)
        u_mec = users_map.get(mecanico_id)
        mec_nom = u_mec.nombre_completo if u_mec else "Mecánico"

        # 3. Asignar mecánico líder/solicitante
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
        attach_mecanico_safe(solicitud, mecanico_entry)

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
                attach_mecanico_safe(solicitud, colab_entry)

        # 5. Actualizar estado y asegurar telemetría de taller
        solicitud.estado = "EN_REPARACION"
        await asegurar_ingreso_taller_y_estadia(self.repo, db, solicitud, now)

        # 6. Comentario predeterminado
        fallas_nombres = [describir_detalle_averia(d) for d in (solicitud.detalles or [])]
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
        attach_comentario_safe(solicitud, comentario_entry, mec_nom)
        solicitud.fecha_actualizacion = now

        await db.commit()
        return orm_to_solicitud_dto(solicitud)

    async def agregar_colaborador(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        dto: AgregarColaboradorDTO,
    ) -> SolicitudDTO:
        """Agrega un nuevo colaborador al equipo de trabajo en caliente."""
        logger.info(
            "[MANTENCION] Agregando colaborador en caliente | solicitud_id=%s | solicitado_por=%s",
            solicitud_id,
            mecanico_id,
        )
        from app.modules.auth.repository.user_repository import user_repository

        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if solicitud.estado != "EN_REPARACION":
            raise BusinessRuleException(
                "Solo se pueden agregar colaboradores cuando la solicitud está EN_REPARACION"
            )

        mecanico_activo = any(
            m.mecanico_id == mecanico_id and m.is_activo for m in solicitud.mecanicos
        )
        if not mecanico_activo:
            raise BusinessRuleException(
                "Solo un mecánico asignado activamente a la solicitud puede agregar colaboradores"
            )

        colab_id = dto.colaborador_id
        if not colab_id and dto.colaborador_nombre:
            encontrados = await user_repository.get_mecanicos_by_nombres_o_usernames(
                db, [dto.colaborador_nombre]
            )
            if not encontrados:
                raise NotFoundException(
                    f"No se encontró un mecánico con nombre '{dto.colaborador_nombre}'"
                )
            colab_id = encontrados[0].id

        if not colab_id:
            raise BusinessRuleException(
                "Debes indicar el ID o nombre del colaborador a agregar"
            )

        if colab_id == mecanico_id:
            raise BusinessRuleException(
                "Un mecánico no puede agregarse a sí mismo como colaborador"
            )

        ya_activo = any(
            m.mecanico_id == colab_id and m.is_activo for m in solicitud.mecanicos
        )
        if ya_activo:
            raise BusinessRuleException(
                "El mecánico ya está activo en esta solicitud"
            )

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
        attach_mecanico_safe(solicitud, colab_entry)
        solicitud.fecha_actualizacion = datetime.now()

        await db.commit()
        return orm_to_solicitud_dto(solicitud)

    async def desasignar_mecanico(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        comentario: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        """Desasignación individual de un mecánico ('[🚪 Salir del Equipo]')."""
        logger.info(
            "[MANTENCION] Desasignando mecánico | solicitud_id=%s | mecanico_id=%s",
            solicitud_id,
            mecanico_id,
        )
        solicitud = await self.repo.get_solicitud_operacional(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()
        mecs_desactivados = await self.repo.desactivar_mecanicos_por_ids(
            db,
            solicitud_id=solicitud.id,
            mecanicos_ids={mecanico_id},
            fecha_desasignacion=now,
        )
        if not mecs_desactivados:
            raise BusinessRuleException(
                "El mecánico no está asignado activamente a esta solicitud"
            )

        await self.repo.desactivar_asignaciones_por_mecanicos(
            db,
            solicitud_id=solicitud.id,
            mecanicos_ids={mecanico_id},
            fecha_desasignacion=now,
        )

        if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
            for m in solicitud.mecanicos:
                if m.mecanico_id == mecanico_id and getattr(m, "is_activo", False):
                    m.is_activo = False
                    m.fecha_desasignacion = now
                    if m.fecha_asignacion:
                        m.duracion_minutos = calcular_duracion_minutos(
                            m.fecha_asignacion, now
                        )

        if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas:
            for asig in solicitud.asignaciones_fallas:
                if asig.mecanico_id == mecanico_id and getattr(asig, "is_activo", False):
                    asig.is_activo = False
                    asig.fecha_desasignacion = now
                    if asig.fecha_asignacion:
                        asig.duracion_minutos = calcular_duracion_minutos(
                            asig.fecha_asignacion, now
                        )

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
        attach_comentario_safe(solicitud, comentario_entry, mec_nom)

        presencias_activas = await self.repo.get_presencias_activas(
            db, solicitud_id=solicitud.id
        )
        if not presencias_activas:
            solicitud.estado = EstadoSolicitud.PENDIENTE.value
            logger.info(
                "[MANTENCION] Sin mecánicos activos → PENDIENTE | solicitud_id=%s",
                solicitud_id,
            )
        solicitud.fecha_actualizacion = now

        await db.commit()
        return orm_to_solicitud_dto(solicitud)

    async def liberar_turno(
        self,
        db: AsyncSession,
        solicitud_id: int,
        usuario_id: int,
        dto: LiberarTurnoDTO,
        usuario_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        """Liberación / Entrega de turno para el equipo completo."""
        logger.info(
            "[MANTENCION] Liberar turno | solicitud_id=%s | usuario_id=%s",
            solicitud_id,
            usuario_id,
        )
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
                        m.duracion_minutos = calcular_duracion_minutos(
                            m.fecha_asignacion, now
                        )

        if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas:
            for asig in solicitud.asignaciones_fallas:
                if getattr(asig, "is_activo", False):
                    asig.is_activo = False
                    asig.fecha_desasignacion = now
                    if asig.fecha_asignacion:
                        asig.duracion_minutos = calcular_duracion_minutos(
                            asig.fecha_asignacion, now
                        )

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
        attach_comentario_safe(solicitud, comentario_entry, usr_nom)
        solicitud.fecha_actualizacion = now

        await db.commit()
        return orm_to_solicitud_dto(solicitud)

    async def autoasignar_fallas(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: AutoasignarFallasDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        """Autoasignación atómica de fallas específicas con soporte de colaboradores."""
        logger.info(
            "[MANTENCION] Autoasignando fallas atómicas | solicitud_id=%s, mecanico_id=%s, fallas=%s",
            solicitud_id,
            mecanico_id,
            dto.detalles_ids,
        )
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if not dto.detalles_ids:
            raise BusinessRuleException(
                "Debe seleccionar al menos una falla para autoasignarse"
            )

        sol_detalles_map = {d.id: d for d in solicitud.detalles}
        for d_id in dto.detalles_ids:
            if d_id not in sol_detalles_map:
                raise NotFoundException(
                    f"La falla con ID {d_id} no pertenece a esta solicitud"
                )

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

        asigs_activas_todas = await self.repo.get_asignaciones_activas(
            db, solicitud_id=solicitud_id, detalles_ids=dto.detalles_ids
        )
        presencias_activas_existentes = (
            await self.repo.get_presencias_activas_mecanicos(
                db, solicitud_id=solicitud_id, mecanicos_ids=mecanicos_objetivo
            )
        )

        for asig in asigs_activas_todas:
            if asig.mecanico_id not in mecanicos_objetivo:
                det_ocupado = sol_detalles_map.get(asig.detalle_id)
                falla_nom = (
                    describir_detalle_averia(det_ocupado)
                    if det_ocupado
                    else f"ID {asig.detalle_id}"
                )
                mec_ocupante = (
                    asig.mecanico.nombre_completo
                    if getattr(asig, "mecanico", None)
                    and getattr(asig.mecanico, "nombre_completo", None)
                    else None
                )
                if not mec_ocupante:
                    u_ocup = await self.repo.get_usuario_by_id(db, asig.mecanico_id)
                    mec_ocupante = (
                        u_ocup.nombre_completo
                        if u_ocup
                        else f"Mecánico #{asig.mecanico_id}"
                    )
                raise BusinessRuleException(
                    f"La falla '{falla_nom}' ya se encuentra tomada activamente por el mecánico {mec_ocupante}. "
                    f"Debe ser liberada antes de que otro mecánico pueda tomarla."
                )

        activas_existentes = {
            (a.mecanico_id, a.detalle_id)
            for a in asigs_activas_todas
            if a.mecanico_id in mecanicos_objetivo
        }

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
                    if (
                        not hasattr(sol_detalles_map[d_id], "asignaciones")
                        or sol_detalles_map[d_id].asignaciones is None
                    ):
                        sol_detalles_map[d_id].asignaciones = []
                    sol_detalles_map[d_id].asignaciones.append(nueva_asig)
                if (
                    not hasattr(solicitud, "asignaciones_fallas")
                    or solicitud.asignaciones_fallas is None
                ):
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
                attach_mecanico_safe(solicitud, nueva_presencia)
                presencias_activas_existentes.add(m_id)

        if solicitud.estado in [
            EstadoSolicitud.PENDIENTE.value,
            EstadoSolicitud.LIBERADO.value,
            EstadoSolicitud.REPORTADO.value,
        ]:
            solicitud.estado = EstadoSolicitud.EN_REPARACION.value
            await asegurar_ingreso_taller_y_estadia(self.repo, db, solicitud, now)

        colab_nombres = []
        if dto.colaboradores_ids:
            for c_id in dto.colaboradores_ids:
                if c_id != mecanico_id:
                    u_c = users_map.get(c_id)
                    if u_c:
                        colab_nombres.append(u_c.nombre_completo)

        fallas_nombres = [
            describir_detalle_averia(sol_detalles_map[d_id])
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
        attach_comentario_safe(solicitud, comentario_entry, mec_nom)
        solicitud.fecha_actualizacion = now

        await db.commit()
        return orm_to_solicitud_dto(solicitud)

    async def asignar_fallas_supervisora(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: AsignarFallasSupervisoraDTO,
        supervisor_id: int,
    ) -> SolicitudDTO:
        """Asignación atómica de fallas realizada por la supervisora a un mecánico específico."""
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
                raise NotFoundException(
                    f"La falla con ID {d_id} no pertenece a esta solicitud"
                )

        now = datetime.now()
        asignadas_count = 0

        from app.modules.auth.repository.user_repository import user_repository

        asigs_exist = await self.repo.get_asignaciones_activas(
            db,
            solicitud_id=solicitud_id,
            detalles_ids=dto.detalles_ids,
            mecanicos_ids=[dto.mecanico_id],
        )
        users_map = await user_repository.get_by_ids_map(
            db, [supervisor_id, dto.mecanico_id]
        )
        presencia = await self.repo.get_presencia_activa_individual(
            db, solicitud_id, dto.mecanico_id
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
                if (
                    not hasattr(sol_detalles_map[d_id], "asignaciones")
                    or sol_detalles_map[d_id].asignaciones is None
                ):
                    sol_detalles_map[d_id].asignaciones = []
                sol_detalles_map[d_id].asignaciones.append(nueva_asig)
            if (
                not hasattr(solicitud, "asignaciones_fallas")
                or solicitud.asignaciones_fallas is None
            ):
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
            attach_mecanico_safe(solicitud, nueva_presencia)

        if solicitud.estado in [
            EstadoSolicitud.PENDIENTE.value,
            EstadoSolicitud.LIBERADO.value,
            EstadoSolicitud.REPORTADO.value,
        ]:
            solicitud.estado = EstadoSolicitud.EN_REPARACION.value
            await asegurar_ingreso_taller_y_estadia(self.repo, db, solicitud, now)

        fallas_nombres = [
            describir_detalle_averia(sol_detalles_map[d_id])
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
        attach_comentario_safe(solicitud, comentario_entry, sup_nom)
        solicitud.fecha_actualizacion = now

        await db.commit()
        return orm_to_solicitud_dto(solicitud)

    async def terminar_avance(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: TerminarAvanceDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        """Cierra el turno o avance del mecánico en sus fallas asignadas, registrando la duración en minutos."""
        logger.info(
            "[MANTENCION] Registrando término de avance | solicitud_id=%s, mecanico_id=%s, fallas=%s",
            solicitud_id,
            mecanico_id,
            dto.detalles_ids,
        )
        solicitud = await self.repo.get_solicitud_con_detalles(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        todas_asigs_activas = await self.repo.get_asignaciones_activas(
            db, solicitud_id=solicitud_id
        )
        presencias_activas = await self.repo.get_presencias_activas(
            db, solicitud_id=solicitud_id
        )

        mi_presencia = next(
            (p for p in presencias_activas if p.mecanico_id == mecanico_id and p.is_activo),
            None,
        )
        mis_asigs_activas = [a for a in todas_asigs_activas if a.mecanico_id == mecanico_id]

        if not mis_asigs_activas and not mi_presencia:
            raise BusinessRuleException(
                "El mecánico no tiene asignaciones ni presencia activa para finalizar avance en esta solicitud"
            )

        sol_detalles_map = {d.id: d for d in solicitud.detalles}

        if dto.detalles_ids:
            target_detalles_ids = set(dto.detalles_ids)
        else:
            target_detalles_ids = {a.detalle_id for a in mis_asigs_activas}

        mis_fallas_ids = {a.detalle_id for a in mis_asigs_activas}
        asignaciones_activas = [
            a
            for a in todas_asigs_activas
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
                asig.duracion_minutos = calcular_duracion_minutos(
                    asig.fecha_asignacion, now
                )
            det = sol_detalles_map.get(asig.detalle_id)
            asig.resuelto_en_esta_asignacion = bool(det and det.resuelto)
            if dto.comentario and dto.comentario.strip():
                asig.comentario = dto.comentario.strip()
            cerradas_asig_ids.add(asig.id)

        con_restantes_ids = set()
        quedan_asignaciones = False
        if cerradas_asig_ids:
            restantes = [a for a in todas_asigs_activas if a.id not in cerradas_asig_ids]
            con_restantes_ids = {
                a.mecanico_id for a in restantes if a.mecanico_id in mecanicos_involucrados_ids
            }
            quedan_asignaciones = len(restantes) > 0

        presencias_cerradas_ids = set()
        for p in presencias_activas:
            if (
                p.mecanico_id in mecanicos_involucrados_ids
                and p.mecanico_id not in con_restantes_ids
            ):
                p.is_activo = False
                p.fecha_desasignacion = now
                if p.fecha_asignacion:
                    p.duracion_minutos = calcular_duracion_minutos(
                        p.fecha_asignacion, now
                    )
                presencias_cerradas_ids.add(p.id)

        quedan_presencias = any(
            p.is_activo for p in presencias_activas if p.id not in presencias_cerradas_ids
        )

        if not quedan_presencias and not quedan_asignaciones:
            solicitud.estado = EstadoSolicitud.PENDIENTE.value
            logger.info(
                "[MANTENCION] Solicitud sin cuadrilla activa → PENDIENTE | solicitud_id=%s",
                solicitud_id,
            )

        for det in (solicitud.detalles or []):
            if hasattr(det, "asignaciones") and det.asignaciones:
                for asig in det.asignaciones:
                    if asig.id in cerradas_asig_ids:
                        asig.is_activo = False
                        asig.fecha_desasignacion = now
                        if asig.fecha_asignacion:
                            asig.duracion_minutos = calcular_duracion_minutos(
                                asig.fecha_asignacion, now
                            )
                        asig.resuelto_en_esta_asignacion = bool(det.resuelto)
                        if dto.comentario and dto.comentario.strip():
                            asig.comentario = dto.comentario.strip()

        if hasattr(solicitud, "asignaciones_fallas") and solicitud.asignaciones_fallas:
            for asig in solicitud.asignaciones_fallas:
                if asig.id in cerradas_asig_ids:
                    asig.is_activo = False
                    asig.fecha_desasignacion = now
                    if asig.fecha_asignacion:
                        asig.duracion_minutos = calcular_duracion_minutos(
                            asig.fecha_asignacion, now
                        )

        if hasattr(solicitud, "mecanicos") and solicitud.mecanicos:
            for mec in solicitud.mecanicos:
                if mec.id in presencias_cerradas_ids:
                    mec.is_activo = False
                    mec.fecha_desasignacion = now
                    if mec.fecha_asignacion:
                        mec.duracion_minutos = calcular_duracion_minutos(
                            mec.fecha_asignacion, now
                        )

        mecanicos_nombres = []
        u_ejecutor = None
        if mecanico_nombre and (
            not mecanicos_involucrados_ids or mecanicos_involucrados_ids == {mecanico_id}
        ):
            ejecutor_nombre = mecanico_nombre
            mecanicos_nombres = [mecanico_nombre]
        else:
            nombres_en_memoria = {}
            for asig in asignaciones_activas:
                if asig.mecanico and asig.mecanico_id:
                    nombres_en_memoria[asig.mecanico_id] = asig.mecanico.nombre_completo
            for p in presencias_activas:
                if getattr(p, "mecanico", None) and p.mecanico_id:
                    nombres_en_memoria[p.mecanico_id] = p.mecanico.nombre_completo

            ids_faltantes = [
                m_id for m_id in mecanicos_involucrados_ids if m_id not in nombres_en_memoria
            ]
            if ids_faltantes:
                from app.modules.auth.repository.user_repository import user_repository

                users_map = await user_repository.get_by_ids_map(db, ids_faltantes)
                for m_id, u in users_map.items():
                    nombres_en_memoria[m_id] = u.nombre_completo

            for m_id in sorted(mecanicos_involucrados_ids):
                mecanicos_nombres.append(nombres_en_memoria.get(m_id, "Mecánico"))

            ejecutor_nombre = nombres_en_memoria.get(mecanico_id) or (
                mecanico_nombre or "Mecánico"
            )

        fallas_involucradas = [
            describir_detalle_averia(sol_detalles_map[a.detalle_id])
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
        attach_comentario_safe(solicitud, comentario_entry, ejecutor_nombre)
        solicitud.fecha_actualizacion = now

        await db.commit()
        return orm_to_solicitud_dto(solicitud)


cuadrilla_service = CuadrillaService()
