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
)


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
                    fecha_creacion=det.fecha_creacion,
                    fecha_resolucion=det.fecha_resolucion,
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

        return SolicitudDTO(
            id=sol.id,
            n_bus=sol.n_bus,
            usuario_creador_id=sol.usuario_creador_id,
            usuario_creador_nombre=creador_nombre,
            mecanico_cierre_id=sol.mecanico_cierre_id,
            mecanico_cierre_nombre=mecanico_cierre_nombre,
            estado=sol.estado,
            descripcion_general=sol.descripcion_general,
            foto_url=sol.foto_url,
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
        sol = await mantencion_repository.get_solicitud_by_id(db, solicitud_id)
        return self._to_solicitud_dto(sol)

    async def create_solicitud(self, db: AsyncSession, dto: SolicitudCreateDTO, creador_id: int) -> SolicitudDTO:
        sol = await mantencion_repository.create_solicitud(db, dto, creador_id)
        return self._to_solicitud_dto(sol)

    async def list_pendientes(self, db: AsyncSession) -> List[SolicitudDTO]:
        solicitudes = await mantencion_repository.list_pendientes(db)
        return [self._to_solicitud_dto(s) for s in solicitudes]

    async def list_mis_trabajos(self, db: AsyncSession, mecanico_id: int) -> List[SolicitudDTO]:
        solicitudes = await mantencion_repository.list_mis_trabajos(db, mecanico_id)
        return [self._to_solicitud_dto(s) for s in solicitudes]

    async def tomar_trabajo(self, db: AsyncSession, solicitud_id: int, lider_id: int, dto: TomarTrabajoDTO) -> SolicitudDTO:
        sol = await mantencion_repository.tomar_trabajo(db, solicitud_id, lider_id, dto)
        return self._to_solicitud_dto(sol)

    async def desasignar_mecanico(self, db: AsyncSession, solicitud_id: int, mecanico_id: int, comentario: Optional[str] = None) -> SolicitudDTO:
        sol = await mantencion_repository.desasignar_mecanico_individual(db, solicitud_id, mecanico_id, comentario)
        return self._to_solicitud_dto(sol)

    async def liberar_turno(self, db: AsyncSession, solicitud_id: int, usuario_id: int, dto: LiberarTurnoDTO) -> SolicitudDTO:
        sol = await mantencion_repository.liberar_turno(db, solicitud_id, usuario_id, dto)
        return self._to_solicitud_dto(sol)

    async def check_detalle(self, db: AsyncSession, solicitud_id: int, detalle_id: int, mecanico_id: int, resuelto: bool) -> SolicitudDTO:
        sol = await mantencion_repository.check_detalle(db, solicitud_id, detalle_id, mecanico_id, resuelto)
        return self._to_solicitud_dto(sol)

    async def agregar_comentario(self, db: AsyncSession, solicitud_id: int, usuario_id: int, dto: ComentarioCreateDTO) -> SolicitudDTO:
        sol = await mantencion_repository.agregar_comentario(db, solicitud_id, usuario_id, dto)
        return self._to_solicitud_dto(sol)

    async def finalizar_solicitud(self, db: AsyncSession, solicitud_id: int, mecanico_cierre_id: int, dto: FinalizarSolicitudDTO) -> SolicitudDTO:
        sol = await mantencion_repository.finalizar_solicitud(db, solicitud_id, mecanico_cierre_id, dto)
        return self._to_solicitud_dto(sol)

    async def list_auditoria(self, db: AsyncSession) -> List[SolicitudDTO]:
        solicitudes = await mantencion_repository.list_auditoria(db)
        return [self._to_solicitud_dto(s) for s in solicitudes]


mantencion_service = MantencionService()
