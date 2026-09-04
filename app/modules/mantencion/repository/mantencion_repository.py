import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.mantencion.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.mantencion.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
from app.modules.mantencion.dtos.mantencion_dto import (
    SolicitudCreateDTO,
    TomarTrabajoDTO,
    LiberarTurnoDTO,
    FinalizarSolicitudDTO,
    ComentarioCreateDTO,
    PautaRespuestaCreateDTO,
    AgregarFallaDTO,
)

logger = logging.getLogger(__name__)


def _calcular_duracion_minutos(inicio: Optional[datetime], fin: Optional[datetime]) -> int:
    """
    Calcula la duración en minutos entre dos datetimes de forma segura,
    removiendo el tzinfo para que la resta sea siempre válida (naive vs aware).
    """
    if not inicio or not fin:
        return 0

    d_inicio = inicio
    d_fin = fin

    if d_inicio.tzinfo is not None and d_fin.tzinfo is None:
        try:
            d_fin = d_fin.astimezone(d_inicio.tzinfo)
        except Exception:
            pass
    elif d_inicio.tzinfo is None and d_fin.tzinfo is not None:
        try:
            d_inicio = d_inicio.astimezone(d_fin.tzinfo)
        except Exception:
            pass

    d_inicio = d_inicio.replace(tzinfo=None) if d_inicio.tzinfo else d_inicio
    d_fin = d_fin.replace(tzinfo=None) if d_fin.tzinfo else d_fin

    delta_seconds = max(0.0, (d_fin - d_inicio).total_seconds())
    return max(1, int(delta_seconds / 60))


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
                selectinload(TallerSolicitud.pauta_respuestas).selectinload(TallerSolicitudPauta.item),
                selectinload(TallerSolicitud.pauta_respuestas).selectinload(TallerSolicitudPauta.mecanico),
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
                falla_id = det_dto.falla_id
                if not falla_id and det_dto.categoria_id:
                    stmt_f = select(FallaTaller.id).where(
                        and_(FallaTaller.categoria_id == det_dto.categoria_id, FallaTaller.is_active == True)
                    ).order_by(FallaTaller.id).limit(1)
                    res_f = await db.execute(stmt_f)
                    falla_id = res_f.scalar_one_or_none()
                    if not falla_id:
                        cat = await db.get(CategoriaFalla, det_dto.categoria_id)
                        cat_nom = cat.nombre if cat else f"Categoría #{det_dto.categoria_id}"
                        nueva_falla = FallaTaller(
                            categoria_id=det_dto.categoria_id,
                            nombre=f"Avería de {cat_nom}",
                            is_active=True,
                        )
                        db.add(nueva_falla)
                        await db.flush()
                        falla_id = nueva_falla.id

                detalle = TallerSolicitudDetalle(
                    solicitud_id=solicitud.id,
                    falla_id=falla_id,
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

        if resuelto and getattr(detalle_target, "falta_repuesto", False):
            raise BusinessRuleException(
                "No se puede marcar como resuelta una falla que se encuentra a la espera de repuesto. "
                "Debe registrarse primero la recepción/disponibilidad del repuesto."
            )

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

        # 1. Validar Checklist / Pauta de Taller Preventiva
        stmt_items = select(PautaTallerItem).where(PautaTallerItem.is_active == True)
        res_items = await db.execute(stmt_items)
        items_activos = list(res_items.scalars().all())
        total_items_pauta = len(items_activos)

        stmt_resp = select(TallerSolicitudPauta).where(TallerSolicitudPauta.solicitud_id == solicitud_id)
        res_resp = await db.execute(stmt_resp)
        respuestas_registradas = list(res_resp.scalars().all())
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

        stmt_asig = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.is_activo == True,
            )
        )
        res_asig = await db.execute(stmt_asig)
        for asig in res_asig.scalars().all():
            asig.is_activo = False
            asig.fecha_desasignacion = now
            if asig.fecha_asignacion:
                asig.duracion_minutos = _calcular_duracion_minutos(asig.fecha_asignacion, now)

        # 4. Liberar bus del taller si corresponde
        if dto.liberar_bus_taller and solicitud.bus_id:
            bus = await db.get(Bus, solicitud.bus_id)
            if bus:
                bus.en_taller = False

        # 5. Registrar comentario de cierre en bitácora
        texto_cierre = "Cierre y liberación de trabajos de taller registrados."
        if dto.comentario_cierre and dto.comentario_cierre.strip():
            texto_cierre += f" Comentario: {dto.comentario_cierre.strip()}."
        if solicitud.motivo_cierre_parcial:
            texto_cierre += f" Motivo cierre parcial: {solicitud.motivo_cierre_parcial}."
        if solicitud.motivo_incompleto_checklist:
            texto_cierre += f" Justificación pauta: {solicitud.motivo_incompleto_checklist}."

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_cierre_id,
            tipo="CIERRE",
            comentario=texto_cierre,
            fecha_registro=now,
        )
        db.add(comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Solicitud FINALIZADA | id=%s, bus_id=%s, bus_liberado=%s",
            solicitud.id,
            solicitud.bus_id,
            dto.liberar_bus_taller,
        )
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
        colaboradores_ids: Optional[List[int]] = None,
    ) -> TallerSolicitud:
        """
        Autoasignación atómica de fallas específicas por parte de un mecánico y opcionalmente colaboradores.
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

        # Lista consolidada de mecánicos a asignar: mecánico principal + colaboradores únicos
        mecanicos_objetivo = [mecanico_id]
        if colaboradores_ids:
            for c_id in colaboradores_ids:
                if c_id not in mecanicos_objetivo:
                    mecanicos_objetivo.append(c_id)

        # Evitar duplicados activos de los mismos mecánicos en las mismas fallas
        stmt_exist = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.mecanico_id.in_(mecanicos_objetivo),
                TallerAsignacionFalla.detalle_id.in_(detalles_ids),
                TallerAsignacionFalla.is_activo == True,
            )
        )
        res_exist = await db.execute(stmt_exist)
        activas_existentes = {(a.mecanico_id, a.detalle_id) for a in res_exist.scalars().all()}

        for m_id in mecanicos_objetivo:
            for d_id in detalles_ids:
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
                db.add(nueva_asig)
                asignadas_count += 1

            # Registrar presencia activa del mecánico en la solicitud (sin rol de líder único)
            mec_rel_stmt = select(TallerSolicitudMecanico).where(
                and_(
                    TallerSolicitudMecanico.solicitud_id == solicitud_id,
                    TallerSolicitudMecanico.mecanico_id == m_id,
                    TallerSolicitudMecanico.is_activo == True,
                )
            )
            res_mec_rel = await db.execute(mec_rel_stmt)
            mec_rel = res_mec_rel.scalar_one_or_none()
            if not mec_rel:
                nueva_presencia = TallerSolicitudMecanico(
                    solicitud_id=solicitud_id,
                    mecanico_id=m_id,
                    asignado_por_id=mecanico_id,
                    es_lider_responsable=False,
                    is_activo=True,
                    fecha_asignacion=now,
                )
                db.add(nueva_presencia)

        if solicitud.estado in ["REPORTADO", "PENDIENTE", "PENDIENTE_REASIGNACION"]:
            solicitud.estado = "EN_REPARACION"

        colab_str = f" y colaboradores {colaboradores_ids}" if colaboradores_ids else ""
        texto_bitacora = f"Mecánico autoasignó {asignadas_count} asignacion(es) de falla(s) específica(s) (IDs: {detalles_ids}){colab_str}"
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
        Finaliza el avance o jornada de trabajo (individual o grupal) en la solicitud.
        Si varios mecánicos estaban trabajando juntos, se cierra el avance para todos los involucrados,
        cronometrando exactamente tiempo de inicio, tiempo de fin y duración en minutos para cada uno.
        La solicitud conmuta a PENDIENTE para ser retomada en el siguiente turno.
        """
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        now = datetime.now()

        stmt_asig = select(TallerAsignacionFalla).where(
            and_(
                TallerAsignacionFalla.solicitud_id == solicitud_id,
                TallerAsignacionFalla.is_activo == True,
            )
        )
        if detalles_ids:
            stmt_asig = stmt_asig.where(TallerAsignacionFalla.detalle_id.in_(detalles_ids))

        res_asig = await db.execute(stmt_asig)
        asignaciones_activas = list(res_asig.scalars().all())

        # Buscar presencias de mecánicos activas
        stmt_presencias = select(TallerSolicitudMecanico).where(
            and_(
                TallerSolicitudMecanico.solicitud_id == solicitud_id,
                TallerSolicitudMecanico.is_activo == True,
            )
        )
        res_presencias = await db.execute(stmt_presencias)
        presencias_activas = list(res_presencias.scalars().all())

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
            if comentario and comentario.strip():
                asig.comentario = comentario.strip()
            mecanicos_involucrados_ids.add(asig.mecanico_id)
            cerradas_asig_ids.add(asig.id)

        # Comprobar para cada mecánico si le quedan otras fallas activas en esta solicitud
        con_restantes_ids = set()
        if detalles_ids and cerradas_asig_ids:
            stmt_restantes = select(TallerAsignacionFalla).where(
                and_(
                    TallerAsignacionFalla.solicitud_id == solicitud_id,
                    TallerAsignacionFalla.mecanico_id.in_(mecanicos_involucrados_ids),
                    TallerAsignacionFalla.is_activo == True,
                    TallerAsignacionFalla.id.not_in(cerradas_asig_ids),
                )
            )
            res_restantes = await db.execute(stmt_restantes)
            con_restantes_ids = {a.mecanico_id for a in res_restantes.scalars().all()}

        presencias_cerradas_ids = set()
        for p in presencias_activas:
            mecanicos_involucrados_ids.add(p.mecanico_id)
            if p.mecanico_id not in con_restantes_ids:
                p.is_activo = False
                p.fecha_desasignacion = now
                if p.fecha_asignacion:
                    p.duracion_minutos = _calcular_duracion_minutos(p.fecha_asignacion, now)
                presencias_cerradas_ids.add(p.id)

        # Comprobar si quedan mecánicos o asignaciones activas en la solicitud
        quedan_presencias = any(p.is_activo for p in presencias_activas if p.id not in presencias_cerradas_ids)

        if detalles_ids and cerradas_asig_ids:
            stmt_otras = select(TallerAsignacionFalla.id).where(
                and_(
                    TallerAsignacionFalla.solicitud_id == solicitud_id,
                    TallerAsignacionFalla.is_activo == True,
                    TallerAsignacionFalla.id.not_in(cerradas_asig_ids),
                )
            )
            res_otras = await db.execute(stmt_otras)
            quedan_asignaciones = bool(res_otras.scalars().all())
        else:
            quedan_asignaciones = False

        if not quedan_presencias and not quedan_asignaciones:
            solicitud.estado = "PENDIENTE"
            logger.info("[MANTENCION] Solicitud sin cuadrilla activa → PENDIENTE | solicitud_id=%s", solicitud_id)

        await db.flush()

        # Mensaje de bitácora detallando equipo o mecánico
        mecanicos_nombres = []
        for m_id in sorted(mecanicos_involucrados_ids):
            u = await db.get(Usuario, m_id)
            mecanicos_nombres.append(u.nombre_completo if u else f"Mecánico #{m_id}")

        u_ejecutor = await db.get(Usuario, mecanico_id)
        ejecutor_nombre = u_ejecutor.nombre_completo if u_ejecutor else f"Mecánico #{mecanico_id}"

        if len(mecanicos_involucrados_ids) > 1:
            texto_bitacora = f"{ejecutor_nombre} finalizó avance grupal para el equipo [{', '.join(mecanicos_nombres)}]"
        else:
            texto_bitacora = f"{ejecutor_nombre} finalizó avance de trabajo"

        if asignaciones_activas:
            texto_bitacora += f" en {len(asignaciones_activas)} asignación(es) de falla"
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
            "[MANTENCION] Avance finalizado (grupal/individual) | solicitud_id=%s, ejecutado_por=%s, involucrados=%s, estado_final=%s",
            solicitud_id,
            mecanico_id,
            list(mecanicos_involucrados_ids),
            solicitud.estado,
        )
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def reportar_repuesto(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        mecanico_id: int,
        falta_repuesto: bool,
        comentario: Optional[str] = None,
    ) -> TallerSolicitud:
        """
        Marca o desmarca si una falla específica no puede continuar por falta de repuestos.
        Registra el evento y comentario en la bitácora de la solicitud.
        """
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        detalle = next((d for d in solicitud.detalles if d.id == detalle_id), None)
        if not detalle:
            raise NotFoundException(f"Detalle con ID {detalle_id} no encontrado en la solicitud")

        if falta_repuesto and getattr(detalle, "resuelto", False):
            raise BusinessRuleException(
                "No se puede reportar falta de repuesto en una falla que ya fue marcada como resuelta. "
                "Si la falla requiere nueva intervención, desmarque primero su resolución."
            )

        detalle.falta_repuesto = falta_repuesto
        detalle.comentario_repuesto = comentario.strip() if comentario else None

        now = datetime.now()
        tipo_accion = "FALTA_REPUESTO" if falta_repuesto else "REPUESTO_DISPONIBLE"
        texto = f"Estado de repuesto para falla #{detalle_id} actualizado: {'FALTA REPUESTO' if falta_repuesto else 'REPUESTO OK'}"
        if comentario and comentario.strip():
            texto += f" - Motivo/Detalle: {comentario.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo=tipo_accion,
            comentario=texto,
            fecha_registro=now,
        )
        db.add(comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Reporte de repuesto | solicitud_id=%s, detalle_id=%s, falta_repuesto=%s",
            solicitud_id,
            detalle_id,
            falta_repuesto,
        )
        return await self.get_solicitud_by_id(db, solicitud_id)

    async def get_pauta_items(self, db: AsyncSession) -> List[PautaTallerItem]:
        """Retorna el catálogo ordenado de ítems activos de la pauta de inspección preventiva."""
        stmt = (
            select(PautaTallerItem)
            .where(PautaTallerItem.is_active == True)
            .order_by(PautaTallerItem.orden.asc(), PautaTallerItem.id.asc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_pauta_respuestas_by_solicitud(
        self, db: AsyncSession, solicitud_id: int
    ) -> List[TallerSolicitudPauta]:
        """Retorna las respuestas de pauta registradas para una solicitud."""
        stmt = (
            select(TallerSolicitudPauta)
            .where(TallerSolicitudPauta.solicitud_id == solicitud_id)
            .options(
                selectinload(TallerSolicitudPauta.item),
                selectinload(TallerSolicitudPauta.mecanico),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def guardar_respuestas_pauta(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        respuestas: List[PautaRespuestaCreateDTO],
    ) -> List[TallerSolicitudPauta]:
        """
        Registra o actualiza en batch las respuestas a los ítems de la pauta preventiva para una solicitud.
        """
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if not respuestas:
            raise BusinessRuleException("Debe enviar al menos una respuesta de pauta")

        now = datetime.now()

        # Obtener respuestas ya existentes para actualizar o insertar
        stmt_exist = select(TallerSolicitudPauta).where(TallerSolicitudPauta.solicitud_id == solicitud_id)
        res_exist = await db.execute(stmt_exist)
        existentes_map = {r.item_id: r for r in res_exist.scalars().all()}

        # Validar ítems
        item_ids = [r.item_id for r in respuestas]
        stmt_items = select(PautaTallerItem.id).where(PautaTallerItem.id.in_(item_ids))
        res_items = await db.execute(stmt_items)
        valid_item_ids = set(res_items.scalars().all())

        for r_dto in respuestas:
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
                db.add(nuevo)

        # Bitácora
        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="CHECKLIST",
            comentario=f"Mecánico registró/actualizó {len(respuestas)} ítem(s) de la pauta preventiva",
            fecha_registro=now,
        )
        db.add(comentario_entry)

        await db.commit()
        return await self.get_pauta_respuestas_by_solicitud(db, solicitud_id)

    async def agregar_falla_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        dto: AgregarFallaDTO,
    ) -> TallerSolicitud:
        """
        Permite a un mecánico o supervisor agregar una nueva avería detectada durante la inspección o reparación.
        Si autoasignar=True, se autoasigna al mecánico y traslada la solicitud a EN_REPARACION.
        """
        solicitud = await self.get_solicitud_by_id(db, solicitud_id)
        if not solicitud:
            raise NotFoundException("Solicitud de taller no encontrada")

        if solicitud.estado == "FINALIZADO":
            raise BusinessRuleException("No se pueden agregar fallas a una solicitud que ya ha sido finalizada")

        now = datetime.now()
        falla_id = dto.falla_id

        # 1. Resolver falla_id si se envió categoria_id
        if not falla_id and dto.categoria_id:
            stmt_f = select(FallaTaller.id).where(
                and_(FallaTaller.categoria_id == dto.categoria_id, FallaTaller.is_active == True)
            ).order_by(FallaTaller.id).limit(1)
            res_f = await db.execute(stmt_f)
            falla_id = res_f.scalar_one_or_none()
            if not falla_id:
                cat = await db.get(CategoriaFalla, dto.categoria_id)
                cat_nom = cat.nombre if cat else f"Categoría #{dto.categoria_id}"
                nueva_falla = FallaTaller(
                    categoria_id=dto.categoria_id,
                    nombre=f"Avería de {cat_nom}",
                    is_active=True,
                )
                db.add(nueva_falla)
                await db.flush()
                falla_id = nueva_falla.id
        elif not falla_id and not dto.categoria_id:
            if not dto.descripcion_personalizada or not dto.descripcion_personalizada.strip():
                raise BusinessRuleException("Debe indicar al menos una categoría, falla o descripción personalizada de la avería")
            # Fallback a categoría 'OTRO'
            stmt_cat_otro = select(CategoriaFalla.id).where(CategoriaFalla.nombre == "OTRO").limit(1)
            res_cat_otro = await db.execute(stmt_cat_otro)
            otro_id = res_cat_otro.scalar_one_or_none()
            if otro_id:
                stmt_f_otro = select(FallaTaller.id).where(
                    and_(FallaTaller.categoria_id == otro_id, FallaTaller.is_active == True)
                ).limit(1)
                falla_id = (await db.execute(stmt_f_otro)).scalar_one_or_none()

        # 2. Crear nuevo detalle de falla
        nuevo_detalle = TallerSolicitudDetalle(
            solicitud_id=solicitud.id,
            falla_id=falla_id,
            descripcion_personalizada=dto.descripcion_personalizada.strip() if dto.descripcion_personalizada else None,
            resuelto=False,
            falta_repuesto=False,
            fecha_creacion=now,
        )
        db.add(nuevo_detalle)
        await db.flush()

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
            db.add(nueva_asig)

            mec_rel_stmt = select(TallerSolicitudMecanico).where(
                and_(
                    TallerSolicitudMecanico.solicitud_id == solicitud.id,
                    TallerSolicitudMecanico.mecanico_id == mecanico_id,
                    TallerSolicitudMecanico.is_activo == True,
                )
            )
            res_mec_rel = await db.execute(mec_rel_stmt)
            if not res_mec_rel.scalar_one_or_none():
                db.add(
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
        u = await db.get(Usuario, mecanico_id)
        mec_nombre = u.nombre_completo if u else f"Mecánico #{mecanico_id}"
        texto_bitacora = f"{mec_nombre} detectó y agregó una nueva avería a la orden"
        if dto.descripcion_personalizada and dto.descripcion_personalizada.strip():
            texto_bitacora += f": {dto.descripcion_personalizada.strip()}"

        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="AVANCE",
            comentario=texto_bitacora,
            fecha_registro=now,
        )
        db.add(comentario_entry)

        await db.commit()
        logger.info(
            "[MANTENCION] Nueva avería agregada a solicitud #%s por mecánico #%s | detalle_id=%s, autoasignar=%s",
            solicitud_id,
            mecanico_id,
            nuevo_detalle.id,
            dto.autoasignar,
        )
        return await self.get_solicitud_by_id(db, solicitud_id)


mantencion_repository = MantencionRepository()



