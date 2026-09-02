import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.mantencion.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.mantencion.dtos.mantencion_dto import (
    SolicitudCreateDTO,
    TomarTrabajoDTO,
    LiberarTurnoDTO,
    FinalizarSolicitudDTO,
    ComentarioCreateDTO,
)

logger = logging.getLogger(__name__)


class MantencionRepository:
    """
    Capa de acceso a datos y lógica transaccional para el módulo de Taller de Mantención.
    """

    async def get_categorias(self, db: AsyncSession) -> List[CategoriaFalla]:
        stmt = select(CategoriaFalla).where(CategoriaFalla.is_active == True)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_fallas(self, db: AsyncSession, categoria_id: Optional[int] = None) -> List[FallaTaller]:
        stmt = select(FallaTaller).where(FallaTaller.is_active == True)
        if categoria_id:
            stmt = stmt.where(FallaTaller.categoria_id == categoria_id)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_solicitud_by_id(self, db: AsyncSession, solicitud_id: int) -> Optional[TallerSolicitud]:
        logger.debug("[MANTENCION] Query get_solicitud_by_id | id=%s", solicitud_id)
        db.expire_all()
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.id == solicitud_id)
            .options(
                selectinload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.asignado_por),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.asignado_por),
            )
        )
        res = await db.execute(stmt)
        sol = res.scalar_one_or_none()
        if not sol:
            logger.warning("[MANTENCION] Solicitud no encontrada | id=%s", solicitud_id)
        return sol


    async def create_solicitud(
        self, db: AsyncSession, dto: SolicitudCreateDTO, creador_id: int
    ) -> TallerSolicitud:
        logger.debug("[MANTENCION] Persistiendo nueva solicitud | n_bus='%s' | creador_id=%s", dto.n_bus, creador_id)
        
        bus_id = dto.bus_id
        if not bus_id and dto.n_bus:
            clean_nb = str(dto.n_bus).strip()
            bus_res = await db.execute(select(Bus.id).where(Bus.n_bus == clean_nb))
            bus_id = bus_res.scalar_one_or_none()

        solicitud = TallerSolicitud(
            n_bus=dto.n_bus,
            bus_id=bus_id,
            usuario_creador_id=creador_id,
            estado="REPORTADO",
            descripcion_general=dto.descripcion_general,
            foto_url=dto.foto_url,
            fecha_creacion=datetime.now(),
        )
        db.add(solicitud)
        await db.flush()

        if dto.detalles:
            for det_dto in dto.detalles:
                detalle = TallerSolicitudDetalle(
                    solicitud_id=solicitud.id,
                    falla_id=det_dto.falla_id,
                    descripcion_personalizada=det_dto.descripcion_personalizada,
                    resuelto=False,
                    fecha_creacion=datetime.now(),
                )
                db.add(detalle)

        await db.commit()
        sol = await self.get_solicitud_by_id(db, solicitud.id)
        logger.info("[MANTENCION] Solicitud persistida | id=%s | n_bus='%s' | bus_id=%s", sol.id, sol.n_bus, sol.bus_id)
        return sol

    async def list_pendientes(self, db: AsyncSession) -> List[TallerSolicitud]:
        """
        Lista buses esperando en taller (Pestaña 1 del Mecánico):
        Buses en estado REPORTADO, PENDIENTE o PENDIENTE_REASIGNACION.
        """
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.estado.in_(["REPORTADO", "PENDIENTE", "PENDIENTE_REASIGNACION"]))
            .order_by(TallerSolicitud.fecha_creacion.asc())
            .options(
                selectinload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.mecanico),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def list_mis_trabajos(self, db: AsyncSession, mecanico_id: int) -> List[TallerSolicitud]:
        """
        Lista buses asignados al mecánico actual (Pestaña 2 del Mecánico):
        Donde el mecánico tiene una asignación activa en taller_solicitud_mecanicos o en taller_asignacion_fallas.
        """
        stmt = (
            select(TallerSolicitud)
            .distinct()
            .outerjoin(
                TallerSolicitudMecanico,
                and_(
                    TallerSolicitudMecanico.solicitud_id == TallerSolicitud.id,
                    TallerSolicitudMecanico.mecanico_id == mecanico_id,
                    TallerSolicitudMecanico.is_activo == True,
                ),
            )
            .outerjoin(
                TallerAsignacionFalla,
                and_(
                    TallerAsignacionFalla.solicitud_id == TallerSolicitud.id,
                    TallerAsignacionFalla.mecanico_id == mecanico_id,
                    TallerAsignacionFalla.is_activo == True,
                ),
            )
            .where(
                and_(
                    or_(TallerSolicitudMecanico.id.isnot(None), TallerAsignacionFalla.id.isnot(None)),
                    TallerSolicitud.estado == "EN_REPARACION",
                )
            )
            .order_by(TallerSolicitud.fecha_creacion.desc())
            .options(
                selectinload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.mecanico),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())


    async def tomar_trabajo(
        self, db: AsyncSession, solicitud_id: int, lider_id: int, dto: TomarTrabajoDTO
    ) -> TallerSolicitud:
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        # 1. Marcar mecánicos previos como inactivos si existieran
        for mec in solicitud.mecanicos:
            if mec.is_activo:
                mec.is_activo = False
                mec.fecha_desasignacion = datetime.now()

        # 2. Asignar líder
        lider_entry = TallerSolicitudMecanico(
            solicitud_id=solicitud.id,
            mecanico_id=lider_id,
            es_lider_responsable=True,
            is_activo=True,
            fecha_asignacion=datetime.now(),
        )
        db.add(lider_entry)
        logger.info("[MANTENCION] Líder asignado | solicitud_id=%s | lider_id=%s", solicitud_id, lider_id)

        # 3. Asignar colaboradores si fueron seleccionados (por IDs o por Nombres)
        target_colab_ids = set(dto.colaboradores_ids or [])
        if dto.colaboradores_nombres:
            from app.modules.auth.repository.user_repository import user_repository
            colab_users = await user_repository.get_mecanicos_by_nombres_o_usernames(db, dto.colaboradores_nombres)
            for u in colab_users:
                target_colab_ids.add(u.id)

        for colab_id in target_colab_ids:
            if colab_id != lider_id:
                colab_entry = TallerSolicitudMecanico(
                    solicitud_id=solicitud.id,
                    mecanico_id=colab_id,
                    es_lider_responsable=False,
                    is_activo=True,
                    fecha_asignacion=datetime.now(),
                )
                db.add(colab_entry)
                logger.info("[MANTENCION] Colaborador asignado | solicitud_id=%s | colab_id=%s", solicitud_id, colab_id)

        # 4. Actualizar estado de la solicitud
        solicitud.estado = "EN_REPARACION"

        # 5. Agregar comentario opcional de inicio/asignación (solo si se envió texto)
        if dto.comentario_inicial and dto.comentario_inicial.strip():
            comentario_entry = TallerSolicitudComentario(
                solicitud_id=solicitud.id,
                usuario_id=lider_id,
                tipo="ASIGNACION",
                comentario=dto.comentario_inicial.strip(),
                fecha_registro=datetime.now(),
            )
            db.add(comentario_entry)

        await db.commit()
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def agregar_colaborador(
        self, db: AsyncSession, solicitud_id: int, lider_id: int, dto
    ) -> TallerSolicitud:
        """
        Agrega un colaborador al equipo de una solicitud EN_REPARACION.
        Solo el líder activo puede invocar esta acción.
        """
        from app.modules.auth.repository.user_repository import user_repository

        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if solicitud.estado != "EN_REPARACION":
            raise BusinessRuleException("Solo se pueden agregar colaboradores cuando la solicitud está EN_REPARACION")

        # Verificar que quien invoca es el líder activo
        es_lider = any(
            m.mecanico_id == lider_id and m.is_activo and m.es_lider_responsable
            for m in solicitud.mecanicos
        )
        if not es_lider:
            raise BusinessRuleException("Solo el mecánico líder activo puede agregar colaboradores")

        # Resolver ID del colaborador (por ID directo o por nombre)
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

        if colab_id == lider_id:
            raise BusinessRuleException("El líder no puede agregarse a sí mismo como colaborador")

        # Verificar que no esté ya activo en la orden
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
        db.add(colab_entry)
        logger.info("[MANTENCION] Colaborador agregado en caliente | solicitud_id=%s | colab_id=%s | por_lider_id=%s", solicitud_id, colab_id, lider_id)

        await db.commit()
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def desasignar_mecanico_individual(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: int, comentario_texto: Optional[str] = None
    ) -> TallerSolicitud:
        """
        Permite a un mecánico desasignarse individualmente de un bus (Botón '[🚪 Salir del Equipo]').
        """
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        # Buscar la asignación activa del mecánico
        mecanico_entry = None
        for mec in solicitud.mecanicos:
            if mec.mecanico_id == mecanico_id and mec.is_activo:
                mecanico_entry = mec
                break

        if not mecanico_entry:
            logger.warning("[MANTENCION] Desasignación fallida: mecánico no activo | solicitud_id=%s | mecanico_id=%s", solicitud_id, mecanico_id)
            raise BusinessRuleException("El mecánico no está asignado activamente a esta solicitud")

        mecanico_entry.is_activo = False
        mecanico_entry.fecha_desasignacion = datetime.now()

        # Registrar comentario de salida (solo si se proporcionó texto)
        if comentario_texto and comentario_texto.strip():
            comentario_entry = TallerSolicitudComentario(
                solicitud_id=solicitud.id,
                usuario_id=mecanico_id,
                tipo="SALIDA_MECANICO",
                comentario=comentario_texto.strip(),
                fecha_registro=datetime.now(),
            )
            db.add(comentario_entry)

        # Verificar mecánicos activos restantes
        activos = [m for m in solicitud.mecanicos if m.is_activo and m.id != mecanico_entry.id]

        if not activos:
            # No queda nadie → volver a pendiente de reasignación
            solicitud.estado = "PENDIENTE_REASIGNACION"
            logger.info("[MANTENCION] Sin mecánicos activos → PENDIENTE_REASIGNACION | solicitud_id=%s", solicitud_id)
        elif mecanico_entry.es_lider_responsable:
            # El líder se fue pero quedan colaboradores → promover al más antiguo
            nuevo_lider = min(activos, key=lambda m: m.fecha_asignacion)
            nuevo_lider.es_lider_responsable = True
            logger.info(
                "[MANTENCION] Líder salió → colaborador promovido a líder | solicitud_id=%s | nuevo_lider_id=%s",
                solicitud_id, nuevo_lider.mecanico_id
            )

        await db.commit()
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def liberar_turno(
        self, db: AsyncSession, solicitud_id: int, usuario_id: int, dto: LiberarTurnoDTO
    ) -> TallerSolicitud:
        """
        Libera el bus para el siguiente turno (Botón '[🔄 Entregar / Pasar Turno]').
        """
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()
        for mec in solicitud.mecanicos:
            if mec.is_activo:
                mec.is_activo = False
                mec.fecha_desasignacion = now

        solicitud.estado = "PENDIENTE_REASIGNACION"

        if dto.comentario and dto.comentario.strip():
            comentario_entry = TallerSolicitudComentario(
                solicitud_id=solicitud.id,
                usuario_id=usuario_id,
                tipo="ENTREGA_TURNO",
                comentario=dto.comentario.strip(),
                fecha_registro=now,
            )
            db.add(comentario_entry)

        await db.commit()
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def check_detalle(
        self, db: AsyncSession, solicitud_id: int, detalle_id: int, mecanico_id: int, resuelto: bool
    ) -> TallerSolicitud:
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        detalle_target = None
        for det in solicitud.detalles:
            if det.id == detalle_id:
                detalle_target = det
                break

        if not detalle_target:
            raise NotFoundException("Detalle de falla no encontrado")

        detalle_target.resuelto = resuelto
        if resuelto:
            detalle_target.mecanico_resolvio_id = mecanico_id
            detalle_target.fecha_resolucion = datetime.now()
        else:
            detalle_target.mecanico_resolvio_id = None
            detalle_target.fecha_resolucion = None

        await db.commit()
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def agregar_comentario(
        self, db: AsyncSession, solicitud_id: int, usuario_id: int, dto: ComentarioCreateDTO
    ) -> TallerSolicitud:
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=usuario_id,
            tipo=dto.tipo if dto.tipo else "GENERAL",
            comentario=dto.comentario,
            fecha_registro=datetime.now(),
        )
        db.add(comentario_entry)

        await db.commit()
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def finalizar_solicitud(
        self, db: AsyncSession, solicitud_id: int, mecanico_cierre_id: int, dto: FinalizarSolicitudDTO
    ) -> TallerSolicitud:
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()
        solicitud.estado = "FINALIZADO"
        solicitud.mecanico_cierre_id = mecanico_cierre_id
        solicitud.fecha_cierre = now

        # Marcar mecánicos activos como completados
        for mec in solicitud.mecanicos:
            if mec.is_activo:
                mec.is_activo = False
                mec.fecha_desasignacion = now

        # Registrar comentario de cierre si se proporcionó
        if dto.comentario_cierre and dto.comentario_cierre.strip():
            comentario_entry = TallerSolicitudComentario(
                solicitud_id=solicitud.id,
                usuario_id=mecanico_cierre_id,
                tipo="CIERRE",
                comentario=dto.comentario_cierre.strip(),
                fecha_registro=now,
            )
            db.add(comentario_entry)

        await db.commit()
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def list_auditoria(self, db: AsyncSession) -> List[TallerSolicitud]:
        """
        Dashboard de trazabilidad completa para Supervisores / Auditores.
        Retorna todas las solicitudes con su historial inmutable de turnos, fallas y comentarios.
        """
        stmt = (
            select(TallerSolicitud)
            .order_by(TallerSolicitud.fecha_creacion.desc())
            .options(
                selectinload(TallerSolicitud.bus),
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.asignaciones).selectinload(TallerAsignacionFalla.mecanico),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
                selectinload(TallerSolicitud.asignaciones_fallas).selectinload(TallerAsignacionFalla.mecanico),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def autoasignar_fallas_mecanico(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalles_ids: List[int],
        mecanico_id: int,
        comentario: Optional[str] = None,
    ) -> TallerSolicitud:
        """
        Autoasignación atómica de fallas específicas por parte de un mecánico.
        Soporta co-responsabilidad: si otro mecánico ya tiene la falla, ambos quedan como responsables activos.
        """
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if not detalles_ids:
            raise BusinessRuleException("Debe seleccionar al menos una falla para autoasignarse")

        sol_detalles_map = {d.id: d for d in solicitud.detalles}
        for d_id in detalles_ids:
            if d_id not in sol_detalles_map:
                raise NotFoundException(f"La falla con ID {d_id} no pertenece a esta solicitud")

        now = datetime.now()
        asignadas_count = 0

        # Evitar duplicados activos del mismo mecánico en la misma falla
        stmt_exist = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.mecanico_id == mecanico_id,
                TallerAsignacionFalla.detalle_id.in_(detalles_ids),
                TallerAsignacionFalla.is_activo == True,
            )
        )
        res_exist = await db.execute(stmt_exist)
        activas_existentes = {a.detalle_id for a in res_exist.scalars().all()}

        for d_id in detalles_ids:
            if d_id in activas_existentes:
                continue

            nueva_asig = TallerAsignacionFalla(
                solicitud_id=solicitud_id,
                detalle_id=d_id,
                mecanico_id=mecanico_id,
                asignado_por_id=mecanico_id,
                origen="AUTOASIGNACION",
                is_activo=True,
                fecha_asignacion=now,
                resuelto_en_esta_asignacion=False,
            )
            db.add(nueva_asig)
            asignadas_count += 1

        # Registrar presencia activa del mecánico en la solicitud (sin rol de líder único)
        mec_rel_stmt = select(TallerSolicitudMecanico).where(
            and_(
                TallerSolicitudMecanico.solicitud_id == solicitud_id,
                TallerSolicitudMecanico.mecanico_id == mecanico_id,
                TallerSolicitudMecanico.is_activo == True,
            )
        )
        res_mec_rel = await db.execute(mec_rel_stmt)
        mec_rel = res_mec_rel.scalar_one_or_none()
        if not mec_rel:
            nueva_presencia = TallerSolicitudMecanico(
                solicitud_id=solicitud_id,
                mecanico_id=mecanico_id,
                asignado_por_id=mecanico_id,
                es_lider_responsable=False,
                is_activo=True,
                fecha_asignacion=now,
            )
            db.add(nueva_presencia)

        if solicitud.estado in ["REPORTADO", "PENDIENTE", "PENDIENTE_REASIGNACION"]:
            solicitud.estado = "EN_REPARACION"

        texto_bitacora = f"Mecánico autoasignó {asignadas_count} falla(s) específica(s) (IDs: {detalles_ids})"
        if comentario and comentario.strip():
            texto_bitacora += f": {comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="ASIGNACION",
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        db.add(comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Fallas autoasignadas | solicitud_id=%s, mecanico_id=%s, count=%s",
            solicitud_id,
            mecanico_id,
            asignadas_count,
        )
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def asignar_fallas_supervisora(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        detalles_ids: List[int],
        supervisor_id: int,
        comentario: Optional[str] = None,
    ) -> TallerSolicitud:
        """
        Asignación de fallas por parte de la Supervisora a un mecánico específico.
        Soporta asignar múltiples mecánicos a la misma falla (co-responsabilidad).
        """
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if not detalles_ids:
            raise BusinessRuleException("Debe indicar al menos una falla para asignar")

        sol_detalles_map = {d.id: d for d in solicitud.detalles}
        for d_id in detalles_ids:
            if d_id not in sol_detalles_map:
                raise NotFoundException(f"La falla con ID {d_id} no pertenece a esta solicitud")

        now = datetime.now()
        asignadas_count = 0

        stmt_exist = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.mecanico_id == mecanico_id,
                TallerAsignacionFalla.detalle_id.in_(detalles_ids),
                TallerAsignacionFalla.is_activo == True,
            )
        )
        res_exist = await db.execute(stmt_exist)
        activas_existentes = {a.detalle_id for a in res_exist.scalars().all()}

        for d_id in detalles_ids:
            if d_id in activas_existentes:
                continue

            nueva_asig = TallerAsignacionFalla(
                solicitud_id=solicitud_id,
                detalle_id=d_id,
                mecanico_id=mecanico_id,
                asignado_por_id=supervisor_id,
                origen="SUPERVISOR",
                is_activo=True,
                fecha_asignacion=now,
                resuelto_en_esta_asignacion=False,
            )
            db.add(nueva_asig)
            asignadas_count += 1

        mec_rel_stmt = select(TallerSolicitudMecanico).where(
            and_(
                TallerSolicitudMecanico.solicitud_id == solicitud_id,
                TallerSolicitudMecanico.mecanico_id == mecanico_id,
                TallerSolicitudMecanico.is_activo == True,
            )
        )
        res_mec_rel = await db.execute(mec_rel_stmt)
        mec_rel = res_mec_rel.scalar_one_or_none()
        if not mec_rel:
            nueva_presencia = TallerSolicitudMecanico(
                solicitud_id=solicitud_id,
                mecanico_id=mecanico_id,
                asignado_por_id=supervisor_id,
                es_lider_responsable=False,
                is_activo=True,
                fecha_asignacion=now,
            )
            db.add(nueva_presencia)

        if solicitud.estado in ["REPORTADO", "PENDIENTE", "PENDIENTE_REASIGNACION"]:
            solicitud.estado = "EN_REPARACION"

        texto_bitacora = f"Supervisora asignó {asignadas_count} falla(s) (IDs: {detalles_ids}) al mecánico #{mecanico_id}"
        if comentario and comentario.strip():
            texto_bitacora += f": {comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=supervisor_id,
            tipo="ASIGNACION",
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        db.add(comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Supervisora asignó fallas | solicitud_id=%s, supervisor_id=%s, mecanico_id=%s, count=%s",
            solicitud_id,
            supervisor_id,
            mecanico_id,
            asignadas_count,
        )
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def terminar_avance(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        detalles_ids: Optional[List[int]] = None,
        comentario: Optional[str] = None,
    ) -> TallerSolicitud:
        """
        Finaliza el avance o jornada individual de un mecánico sobre sus fallas asignadas.
        Calcula duración en minutos y registra si resolvió o no en esta asignación.
        Si no quedan mecánicos activos en la orden, pasa a PENDIENTE.
        """
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        stmt = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.mecanico_id == mecanico_id,
                TallerAsignacionFalla.is_activo == True,
            )
        )
        if detalles_ids:
            stmt = stmt.where(TallerAsignacionFalla.detalle_id.in_(detalles_ids))

        res = await db.execute(stmt)
        asignaciones_activas = list(res.scalars().all())

        if not asignaciones_activas:
            raise BusinessRuleException("El mecánico no tiene asignaciones activas para finalizar avance")

        sol_detalles_map = {d.id: d for d in solicitud.detalles}

        for asig in asignaciones_activas:
            asig.is_activo = False
            asig.fecha_desasignacion = now
            if asig.fecha_asignacion:
                delta = (now - asig.fecha_asignacion).total_seconds() / 60
                asig.duracion_minutos = max(1, int(delta))
            det = sol_detalles_map.get(asig.detalle_id)
            asig.resuelto_en_esta_asignacion = bool(det and det.resuelto)
            if comentario and comentario.strip():
                asig.comentario = comentario.strip()

        # Comprobar si al mecánico le quedan otras fallas activas en la solicitud
        stmt_restantes_mec = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.mecanico_id == mecanico_id,
                TallerAsignacionFalla.is_activo == True,
            )
        )
        res_rest_mec = await db.execute(stmt_restantes_mec)
        if not res_rest_mec.scalars().all():
            stmt_pres = select(TallerSolicitudMecanico).where(
                and_(
                    TallerSolicitudMecanico.solicitud_id == solicitud_id,
                    TallerSolicitudMecanico.mecanico_id == mecanico_id,
                    TallerSolicitudMecanico.is_activo == True,
                )
            )
            res_pres = await db.execute(stmt_pres)
            presencias = res_pres.scalars().all()
            for p in presencias:
                p.is_activo = False
                p.fecha_desasignacion = now
                if p.fecha_asignacion:
                    p.duracion_minutos = max(1, int((now - p.fecha_asignacion).total_seconds() / 60))

        # Comprobar si quedan CUALQUIER mecánico activo en la solicitud
        stmt_total_activas = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.is_activo == True,
            )
        )
        res_total = await db.execute(stmt_total_activas)
        total_activas = list(res_total.scalars().all())

        if not total_activas:
            solicitud.estado = "PENDIENTE"

        texto_bitacora = f"Mecánico finalizó avance en {len(asignaciones_activas)} falla(s)"
        if comentario and comentario.strip():
            texto_bitacora += f": {comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="ENTREGA_TURNO",
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        db.add(comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Avance finalizado | solicitud_id=%s, mecanico_id=%s, fallas_cerradas=%s, estado_final=%s",
            solicitud_id,
            mecanico_id,
            len(asignaciones_activas),
            solicitud.estado,
        )
        return await self.get_solicitud_by_id(db, solicitud_id)


mantencion_repository = MantencionRepository()

