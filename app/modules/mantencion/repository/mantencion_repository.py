from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.mantencion.dtos.mantencion_dto import (
    SolicitudCreateDTO,
    TomarTrabajoDTO,
    LiberarTurnoDTO,
    FinalizarSolicitudDTO,
    ComentarioCreateDTO,
)


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
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.id == solicitud_id)
            .options(
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
            )
        )
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def create_solicitud(
        self, db: AsyncSession, dto: SolicitudCreateDTO, creador_id: int
    ) -> TallerSolicitud:
        solicitud = TallerSolicitud(
            n_bus=dto.n_bus,
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
        return await self.get_solicitud_by_id(db, solicitud.id)

    async def list_pendientes(self, db: AsyncSession) -> List[TallerSolicitud]:
        """
        Lista buses esperando en taller (Pestaña 1 del Mecánico):
        Buses en estado REPORTADO o PENDIENTE_REASIGNACION.
        """
        stmt = (
            select(TallerSolicitud)
            .where(TallerSolicitud.estado.in_(["REPORTADO", "PENDIENTE_REASIGNACION"]))
            .order_by(TallerSolicitud.fecha_creacion.asc())
            .options(
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def list_mis_trabajos(self, db: AsyncSession, mecanico_id: int) -> List[TallerSolicitud]:
        """
        Lista buses asignados al mecánico actual (Pestaña 2 del Mecánico):
        Donde el mecánico tiene un registro en taller_solicitud_mecanicos con is_activo = True.
        """
        stmt = (
            select(TallerSolicitud)
            .join(TallerSolicitudMecanico)
            .where(
                and_(
                    TallerSolicitudMecanico.mecanico_id == mecanico_id,
                    TallerSolicitudMecanico.is_activo == True,
                    TallerSolicitud.estado == "EN_REPARACION",
                )
            )
            .order_by(TallerSolicitud.fecha_creacion.desc())
            .options(
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
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

        # 3. Asignar colaboradores si fueron seleccionados
        if dto.colaboradores_ids:
            for colab_id in dto.colaboradores_ids:
                if colab_id != lider_id:
                    colab_entry = TallerSolicitudMecanico(
                        solicitud_id=solicitud.id,
                        mecanico_id=colab_id,
                        es_lider_responsable=False,
                        is_activo=True,
                        fecha_asignacion=datetime.now(),
                    )
                    db.add(colab_entry)

        # 4. Actualizar estado de la solicitud
        solicitud.estado = "EN_REPARACION"

        # 5. Agregar comentario opcional de inicio/asignación
        texto_comentario = dto.comentario_inicial if dto.comentario_inicial else "Equipo de mecánicos tomó la orden de mantención."
        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=lider_id,
            tipo="ASIGNACION",
            comentario=texto_comentario,
            fecha_registro=datetime.now(),
        )
        db.add(comentario_entry)

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
            raise BusinessRuleException("El mecánico no está asignado activamente a esta solicitud")

        mecanico_entry.is_activo = False
        mecanico_entry.fecha_desasignacion = datetime.now()

        # Registrar comentario de salida
        txt = comentario_texto if comentario_texto else "Mecanico se retiró individualmente del equipo."
        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_id,
            tipo="SALIDA_MECANICO",
            comentario=txt,
            fecha_registro=datetime.now(),
        )
        db.add(comentario_entry)

        # Verificar si quedan mecánicos activos en el equipo. Si no queda ninguno, volver a PENDIENTE_REASIGNACION
        activos = [m for m in solicitud.mecanicos if m.is_activo and m.id != mecanico_entry.id]
        if not activos:
            solicitud.estado = "PENDIENTE_REASIGNACION"

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

        txt = dto.comentario if dto.comentario else "Turno entregado / liberado para el siguiente equipo de mecánicos."
        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=usuario_id,
            tipo="ENTREGA_TURNO",
            comentario=txt,
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

        # Registrar comentario de cierre
        txt = dto.comentario_cierre if dto.comentario_cierre else "Trabajos de taller completados. Bus pasa a estado DISPONIBLE."
        comentario_entry = TallerSolicitudComentario(
            solicitud_id=solicitud.id,
            usuario_id=mecanico_cierre_id,
            tipo="CIERRE",
            comentario=txt,
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
                selectinload(TallerSolicitud.creador),
                selectinload(TallerSolicitud.mecanico_cierre),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.falla),
                selectinload(TallerSolicitud.detalles).selectinload(TallerSolicitudDetalle.mecanico_resolvio),
                selectinload(TallerSolicitud.mecanicos).selectinload(TallerSolicitudMecanico.mecanico),
                selectinload(TallerSolicitud.comentarios).selectinload(TallerSolicitudComentario.usuario),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())


mantencion_repository = MantencionRepository()
