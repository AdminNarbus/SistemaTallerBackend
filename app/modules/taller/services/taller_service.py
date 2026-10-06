import logging
from datetime import datetime
from typing import Any, List, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.taller.constants import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_PAGE_SKIP,
)
from app.modules.taller.dtos import (
    AgregarColaboradorDTO,
    AgregarFallaDTO,
    AsignarFallasSupervisoraDTO,
    AutoasignarFallasDTO,
    CambiarEstadoSolicitudDTO,
    CategoriaFallaDTO,
    ComentarioAddedDTO,
    ComentarioCreateDTO,
    DetalleUpdateDTO,
    FallaTallerDTO,
    FinalizarSolicitudDTO,
    LiberarSolicitudDTO,
    LiberarTurnoDTO,
    PautaBatchUpdateDTO,
    PautaEstadoResumenDTO,
    PautaTallerItemDTO,
    ReportarRepuestoDTO,
    ResolverFallaSupervisoraDTO,
    SolicitudCreateDTO,
    SolicitudDTO,
    SolicitudResumenDTO,
    TerminarAvanceDTO,
    TomarTrabajoDTO,
)
from app.modules.taller.repository.taller_repository import (
    TallerRepository,
    taller_repository,
)
from app.modules.taller.services.taller_catalogo_service import (
    TallerCatalogoService,
    taller_catalogo_service,
)
from app.modules.taller.services.pauta_service import (
    PautaService,
    pauta_service,
)
from app.modules.taller.services.solicitud_service import (
    SolicitudService,
    solicitud_service,
)
from app.modules.taller.services.cuadrilla_service import (
    CuadrillaService,
    cuadrilla_service,
)
from app.modules.taller.services.averias_service import (
    AveriasService,
    averias_service,
)
from app.modules.taller.services.cierre_service import (
    CierreService,
    cierre_service,
)
from app.modules.taller.services.mappers import (
    mapear_a_solicitud_dto,
    dict_to_solicitud_dto,
    dict_to_solicitud_resumen_dto,
    orm_to_solicitud_dto,
)
from app.modules.taller.services.estadias_helper import (
    asegurar_ingreso_taller_y_estadia,
    cerrar_estadia_activa,
    attach_comentario_safe,
    attach_mecanico_safe,
)

logger = logging.getLogger(__name__)


class TallerService:
    """
    Fachada orquestadora para compatibilidad y pruebas de integración.
    Delega directamente en los servicios atómicos especializados:
    - TallerCatalogoService
    - PautaService
    - SolicitudService
    - CuadrillaService
    - AveriasService
    - CierreService
    """

    def __init__(
        self,
        repository: Optional[TallerRepository] = None,
        storage: Optional[Any] = None,
        catalogo_srv: Optional[TallerCatalogoService] = None,
        pauta_srv: Optional[PautaService] = None,
        solicitud_srv: Optional[SolicitudService] = None,
        cuadrilla_srv: Optional[CuadrillaService] = None,
        averias_srv: Optional[AveriasService] = None,
        cierre_srv: Optional[CierreService] = None,
    ) -> None:
        self.repo = repository or taller_repository
        self.storage = storage or getattr(solicitud_service, "storage", None)

        self.catalogo_srv = catalogo_srv or (
            TallerCatalogoService(repository=self.repo)
            if repository
            else taller_catalogo_service
        )
        self.pauta_srv = pauta_srv or (
            PautaService(repository=self.repo) if repository else pauta_service
        )
        self.solicitud_srv = solicitud_srv or (
            SolicitudService(repository=self.repo, storage=self.storage)
            if (repository or storage)
            else solicitud_service
        )
        self.cuadrilla_srv = cuadrilla_srv or (
            CuadrillaService(repository=self.repo) if repository else cuadrilla_service
        )
        self.averias_srv = averias_srv or (
            AveriasService(repository=self.repo) if repository else averias_service
        )
        self.cierre_srv = cierre_srv or (
            CierreService(repository=self.repo) if repository else cierre_service
        )

    # --- Mapeos y Ayudantes de Compatibilidad ---

    def _attach_comentario_safe(
        self, solicitud, comentario, usuario_nombre: Optional[str] = None
    ) -> None:
        attach_comentario_safe(solicitud, comentario, usuario_nombre)

    def _attach_mecanico_safe(self, solicitud, mecanico) -> None:
        attach_mecanico_safe(solicitud, mecanico)

    def mapear_a_solicitud_dto(self, item: Any) -> Optional[SolicitudDTO]:
        return mapear_a_solicitud_dto(item, storage=self.solicitud_srv.storage)

    def _to_solicitud_dto(self, sol) -> Optional[SolicitudDTO]:
        return orm_to_solicitud_dto(sol, storage=self.solicitud_srv.storage)

    def _dict_to_solicitud_dto(self, r: dict) -> SolicitudDTO:
        return dict_to_solicitud_dto(r, storage=self.solicitud_srv.storage)

    def _dict_to_solicitud_resumen_dto(
        self, r: dict, mecanico_id: Optional[int] = None
    ) -> SolicitudResumenDTO:
        return dict_to_solicitud_resumen_dto(
            r, storage=self.solicitud_srv.storage, mecanico_id=mecanico_id
        )

    async def _asegurar_ingreso_taller_y_estadia(
        self, db: AsyncSession, solicitud: Any, now: datetime
    ) -> None:
        await asegurar_ingreso_taller_y_estadia(self.repo, db, solicitud, now)

    async def _cerrar_estadia_activa(
        self, db: AsyncSession, solicitud: Any, now: datetime, motivo_salida: str
    ) -> None:
        await cerrar_estadia_activa(self.repo, db, solicitud, now, motivo_salida)

    # --- Catálogos ---

    async def get_categorias(self, db: AsyncSession) -> List[CategoriaFallaDTO]:
        return await self.catalogo_srv.get_categorias(db)

    async def get_fallas(
        self, db: AsyncSession, categoria_id: Optional[int] = None
    ) -> List[FallaTallerDTO]:
        return await self.catalogo_srv.get_fallas(db, categoria_id)

    async def get_pauta_items(self, db: AsyncSession) -> List[PautaTallerItemDTO]:
        return await self.pauta_srv.get_pauta_items(db)

    # --- Pauta Preventiva ---

    async def get_pauta_resumen(
        self, db: AsyncSession, solicitud_id: int
    ) -> PautaEstadoResumenDTO:
        return await self.pauta_srv.get_pauta_resumen(db, solicitud_id)

    async def guardar_respuestas_pauta(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: PautaBatchUpdateDTO,
        mecanico_id: int,
    ) -> PautaEstadoResumenDTO:
        result = await self.pauta_srv.guardar_respuestas_pauta(
            db, solicitud_id, dto, mecanico_id
        )
        return result

    # --- Solicitudes ---

    async def get_solicitud(self, db: AsyncSession, solicitud_id: int) -> SolicitudDTO:
        return await self.solicitud_srv.get_solicitud(db, solicitud_id)

    async def list_pendientes(
        self,
        db: AsyncSession,
        limit: Optional[int] = DEFAULT_PAGE_LIMIT,
        skip: int = DEFAULT_PAGE_SKIP,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
        estado: Optional[str] = None,
    ) -> List[SolicitudResumenDTO]:
        return await self.solicitud_srv.list_pendientes(
            db, limit=limit, skip=skip, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, estado=estado
        )

    async def count_pendientes(
        self,
        db: AsyncSession,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
        estado: Optional[str] = None,
    ) -> int:
        return await self.solicitud_srv.count_pendientes(
            db, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, estado=estado
        )

    async def list_mis_trabajos(
        self,
        db: AsyncSession,
        mecanico_id: int,
        limit: Optional[int] = DEFAULT_PAGE_LIMIT,
        skip: int = DEFAULT_PAGE_SKIP,
    ) -> List[SolicitudResumenDTO]:
        return await self.solicitud_srv.list_mis_trabajos(
            db, mecanico_id, limit=limit, skip=skip
        )

    async def count_mis_trabajos(self, db: AsyncSession, mecanico_id: int) -> int:
        return await self.solicitud_srv.count_mis_trabajos(db, mecanico_id=mecanico_id)

    async def list_auditoria(self, db: AsyncSession) -> List[SolicitudDTO]:
        return await self.solicitud_srv.list_auditoria(db)

    async def create_solicitud(
        self,
        db: AsyncSession,
        dto: SolicitudCreateDTO,
        creador_id: int,
        creador_nombre: Optional[str] = None,
        creador_rol: Optional[str] = None,
        foto: Optional[UploadFile] = None,
        fotos: Optional[List[UploadFile]] = None,
    ) -> SolicitudDTO:
        result = await self.solicitud_srv.create_solicitud(
            db,
            dto,
            creador_id=creador_id,
            creador_nombre=creador_nombre,
            creador_rol=creador_rol,
            foto=foto,
            fotos=fotos,
        )
        return result

    # --- Cuadrilla ---

    async def tomar_trabajo(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        dto: TomarTrabajoDTO,
    ) -> SolicitudDTO:
        result = await self.cuadrilla_srv.tomar_trabajo(
            db, solicitud_id=solicitud_id, mecanico_id=mecanico_id, dto=dto
        )
        return result

    async def agregar_colaborador(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        dto: AgregarColaboradorDTO,
    ) -> SolicitudDTO:
        result = await self.cuadrilla_srv.agregar_colaborador(
            db, solicitud_id=solicitud_id, mecanico_id=mecanico_id, dto=dto
        )
        return result

    async def desasignar_mecanico(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        comentario: Optional[str] = None,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        result = await self.cuadrilla_srv.desasignar_mecanico(
            db,
            solicitud_id=solicitud_id,
            mecanico_id=mecanico_id,
            comentario=comentario,
            mecanico_nombre=mecanico_nombre,
        )
        return result

    async def liberar_turno(
        self,
        db: AsyncSession,
        solicitud_id: int,
        usuario_id: int,
        dto: LiberarTurnoDTO,
        usuario_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        result = await self.cuadrilla_srv.liberar_turno(
            db,
            solicitud_id=solicitud_id,
            usuario_id=usuario_id,
            dto=dto,
            usuario_nombre=usuario_nombre,
        )
        return result

    async def autoasignar_fallas(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: AutoasignarFallasDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        result = await self.cuadrilla_srv.autoasignar_fallas(
            db,
            solicitud_id=solicitud_id,
            dto=dto,
            mecanico_id=mecanico_id,
            mecanico_nombre=mecanico_nombre,
        )
        return result

    async def asignar_fallas_supervisora(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: AsignarFallasSupervisoraDTO,
        supervisor_id: int,
    ) -> SolicitudDTO:
        result = await self.cuadrilla_srv.asignar_fallas_supervisora(
            db,
            solicitud_id=solicitud_id,
            dto=dto,
            supervisor_id=supervisor_id,
        )
        return result

    async def terminar_avance(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: TerminarAvanceDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        result = await self.cuadrilla_srv.terminar_avance(
            db,
            solicitud_id=solicitud_id,
            dto=dto,
            mecanico_id=mecanico_id,
            mecanico_nombre=mecanico_nombre,
        )
        return result

    # --- Averías ---

    async def agregar_falla(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_id: int,
        dto: AgregarFallaDTO,
    ) -> SolicitudDTO:
        result = await self.averias_srv.agregar_falla(
            db, solicitud_id=solicitud_id, mecanico_id=mecanico_id, dto=dto
        )
        return result

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
        result = await self.averias_srv.check_detalle(
            db,
            solicitud_id=solicitud_id,
            detalle_id=detalle_id,
            mecanico_id=mecanico_id,
            resuelto=resuelto,
            mecanico_nombre=mecanico_nombre,
            mecanico_resolvio_id=mecanico_resolvio_id,
        )
        return result

    async def reportar_repuesto(
        self,
        db: AsyncSession,
        solicitud_id: int,
        detalle_id: int,
        dto: ReportarRepuestoDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> DetalleUpdateDTO:
        result = await self.averias_srv.reportar_repuesto(
            db,
            solicitud_id=solicitud_id,
            detalle_id=detalle_id,
            dto=dto,
            mecanico_id=mecanico_id,
            mecanico_nombre=mecanico_nombre,
        )
        return result

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
        result = await self.averias_srv.resolver_falla_supervisora(
            db,
            solicitud_id=solicitud_id,
            detalle_id=detalle_id,
            dto=dto,
            supervisor_id=supervisor_id,
            supervisor_nombre=supervisor_nombre,
            fotos=fotos,
        )
        return result

    # --- Cierre / Finalización / Bitácora ---

    async def agregar_comentario(
        self,
        db: AsyncSession,
        solicitud_id: int,
        usuario_id: int,
        dto: ComentarioCreateDTO,
        usuario_nombre: Optional[str] = None,
    ) -> ComentarioAddedDTO:
        result = await self.cierre_srv.agregar_comentario(
            db,
            solicitud_id=solicitud_id,
            usuario_id=usuario_id,
            dto=dto,
            usuario_nombre=usuario_nombre,
        )
        return result

    async def finalizar_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        mecanico_cierre_id: int,
        dto: FinalizarSolicitudDTO,
        mecanico_cierre_nom: Optional[str] = None,
    ) -> SolicitudDTO:
        result = await self.cierre_srv.finalizar_solicitud(
            db,
            solicitud_id=solicitud_id,
            mecanico_cierre_id=mecanico_cierre_id,
            dto=dto,
            mecanico_cierre_nom=mecanico_cierre_nom,
        )
        return result

    async def liberar_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: LiberarSolicitudDTO,
        mecanico_id: int,
        mecanico_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        result = await self.cierre_srv.liberar_solicitud(
            db,
            solicitud_id=solicitud_id,
            dto=dto,
            mecanico_id=mecanico_id,
            mecanico_nombre=mecanico_nombre,
        )
        return result

    async def cambiar_estado_solicitud(
        self,
        db: AsyncSession,
        solicitud_id: int,
        dto: CambiarEstadoSolicitudDTO,
        supervisor_id: int,
        supervisor_nombre: Optional[str] = None,
    ) -> SolicitudDTO:
        result = await self.cierre_srv.cambiar_estado_solicitud(
            db,
            solicitud_id=solicitud_id,
            dto=dto,
            supervisor_id=supervisor_id,
            supervisor_nombre=supervisor_nombre,
        )
        return result


taller_service = TallerService()
