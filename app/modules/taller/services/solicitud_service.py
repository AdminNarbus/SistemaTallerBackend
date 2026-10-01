import logging
from datetime import datetime
from typing import Any, List, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.storage.storage_service import storage_service, StorageService
from app.modules.auth.constants import RolUsuario
from app.modules.taller.constants import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_PAGE_SKIP,
    EstadoSolicitud,
)
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_estadia import TallerSolicitudEstadia
from app.modules.taller.models.taller_solicitud_evidencia import TallerSolicitudEvidencia
from app.modules.taller.dtos import (
    CategoriaFallaDTO,
    EstadiaTallerDTO,
    FallaTallerDTO,
    SolicitudCreateDTO,
    SolicitudDetalleDTO,
    SolicitudDTO,
    SolicitudEvidenciaDTO,
    SolicitudResumenDTO,
)
from app.modules.taller.repository.taller_repository import (
    TallerRepository,
    taller_repository,
)
from app.modules.taller.utils import recopilar_archivos_fotos
from app.modules.taller.services.mappers import (
    dict_to_solicitud_dto,
    dict_to_solicitud_resumen_dto,
    orm_to_solicitud_dto,
    orm_to_solicitud_resumen_dto,
)

logger = logging.getLogger(__name__)


class SolicitudService:
    """
    Servicio de capa de negocio responsable de la creación, consulta unitaria,
    listados paginados y auditoría de Órdenes de Trabajo (Solicitudes de Taller).
    """

    def __init__(
        self,
        repository: Optional[TallerRepository] = None,
        storage: Optional[StorageService] = None,
    ) -> None:
        self.repo = repository or taller_repository
        self.storage = storage or storage_service

    async def get_solicitud(self, db: AsyncSession, solicitud_id: int) -> SolicitudDTO:
        """Obtiene el detalle completo de una solicitud por su ID en 1 solo viaje de red o fallback ORM."""
        logger.debug("[MANTENCION] Consultando solicitud | id=%s", solicitud_id)
        sol = await self.repo.get_solicitud_dto_by_id(db, solicitud_id)
        if not sol:
            raise NotFoundException("Solicitud de taller no encontrada")
        if isinstance(sol, dict):
            return dict_to_solicitud_dto(sol, storage=self.storage)
        return orm_to_solicitud_dto(sol, storage=self.storage)

    async def list_pendientes(
        self,
        db: AsyncSession,
        limit: Optional[int] = DEFAULT_PAGE_LIMIT,
        skip: int = DEFAULT_PAGE_SKIP,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
    ) -> List[SolicitudResumenDTO]:
        """Pestaña 1 Mecánico: Buses esperando en taller (REPORTADO / PENDIENTE)."""
        logger.debug(
            "[MANTENCION] Listando solicitudes pendientes | limit=%s | skip=%s | fecha_desde=%s | fecha_hasta=%s",
            limit,
            skip,
            fecha_desde,
            fecha_hasta,
        )
        solicitudes = await self.repo.list_pendientes(
            db, limit=limit, skip=skip, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
        )
        results = []
        for s in solicitudes:
            if isinstance(s, dict):
                results.append(dict_to_solicitud_resumen_dto(s, storage=self.storage))
            else:
                results.append(
                    orm_to_solicitud_resumen_dto(s, storage=self.storage)
                )
        return results

    async def count_pendientes(
        self,
        db: AsyncSession,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
    ) -> int:
        """Retorna el conteo total de solicitudes pendientes en taller."""
        return await self.repo.count_pendientes(
            db, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
        )

    async def list_mis_trabajos(
        self,
        db: AsyncSession,
        mecanico_id: int,
        limit: Optional[int] = DEFAULT_PAGE_LIMIT,
        skip: int = DEFAULT_PAGE_SKIP,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
    ) -> List[SolicitudResumenDTO]:
        """Pestaña 2 Mecánico: Buses asignados activamente al mecánico."""
        logger.debug(
            "[MANTENCION] Listando trabajos activos | mecanico_id=%s, limit=%s, skip=%s | fecha_desde=%s | fecha_hasta=%s",
            mecanico_id,
            limit,
            skip,
            fecha_desde,
            fecha_hasta,
        )
        solicitudes = await self.repo.list_mis_trabajos(
            db,
            mecanico_id,
            limit=limit,
            skip=skip,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
        results = []
        for s in solicitudes:
            if isinstance(s, dict):
                results.append(
                    dict_to_solicitud_resumen_dto(
                        s, storage=self.storage, mecanico_id=mecanico_id
                    )
                )
            else:
                results.append(
                    orm_to_solicitud_resumen_dto(
                        s, storage=self.storage, mecanico_id=mecanico_id
                    )
                )
        return results

    async def count_mis_trabajos(
        self,
        db: AsyncSession,
        mecanico_id: int,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
    ) -> int:
        """Retorna el conteo total de trabajos activos del mecánico."""
        return await self.repo.count_mis_trabajos(
            db,
            mecanico_id=mecanico_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )

    async def list_auditoria(self, db: AsyncSession) -> List[SolicitudDTO]:
        """Retorna el historial completo de solicitudes para auditoría."""
        logger.debug("[MANTENCION] Consultando auditoría completa de solicitudes")
        solicitudes = await self.repo.list_auditoria(db)
        return [orm_to_solicitud_dto(s, storage=self.storage) for s in solicitudes]

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
        """Crea una nueva solicitud de taller con manejo de evidencias, detalles y estadías."""
        logger.info(
            "[MANTENCION] Creando solicitud | n_bus='%s' | bus_id=%s | creador_id=%s | rol=%s",
            dto.n_bus,
            dto.bus_id,
            creador_id,
            creador_rol,
        )

        archivos_fotos = recopilar_archivos_fotos(foto=foto, fotos=fotos)

        uploaded_evidencias: List[dict] = []
        for f in archivos_fotos:
            upload_res = await self.storage.upload_image(file=f, folder="solicitudes")
            uploaded_evidencias.append(upload_res)
            logger.info(
                "[MANTENCION] Evidencia de solicitud subida | path='%s' | url='%s' | tamano=%s bytes",
                upload_res.get("path"),
                upload_res.get("url"),
                upload_res.get("size_bytes"),
            )

        if dto.fotos_urls:
            for u in dto.fotos_urls:
                if u and not any(
                    e.get("path") == u or e.get("url") == u for e in uploaded_evidencias
                ):
                    uploaded_evidencias.append({
                        "path": u,
                        "url": self.storage.get_url(u) or u,
                        "original_filename": None,
                        "size_bytes": None,
                        "content_type": None,
                    })

        if uploaded_evidencias and not dto.foto_url:
            dto.foto_url = uploaded_evidencias[0].get("path") or uploaded_evidencias[0]["url"]
        elif dto.foto_url and not any(
            e.get("path") == dto.foto_url or e.get("url") == dto.foto_url
            for e in uploaded_evidencias
        ):
            uploaded_evidencias.insert(0, {
                "path": dto.foto_url,
                "url": self.storage.get_url(dto.foto_url) or dto.foto_url,
                "original_filename": None,
                "size_bytes": None,
                "content_type": None,
            })

        # 1. Resolver bus_id y patente
        bus_id = dto.bus_id
        bus_patente = dto.bus_patente
        n_bus = dto.n_bus
        bus_obj = None

        if bus_id and n_bus:
            logger.debug(
                "[MANTENCION] Bus resuelto directamente desde frontend | bus_id=%s, n_bus='%s'",
                bus_id,
                n_bus,
            )
        elif dto.n_bus:
            bus_info = await self.repo.get_bus_info_by_n_bus(db, dto.n_bus)
            if bus_info:
                bus_id, bus_patente = bus_info
        elif bus_id:
            bus_obj = await self.repo.get_bus_by_id(db, bus_id)
            if bus_obj:
                bus_patente = bus_obj.patente
                n_bus = bus_obj.n_bus

        # 2. Creador de la solicitud
        if not creador_nombre or not creador_rol:
            u_creador = await self.repo.get_usuario_by_id(db, creador_id)
            if u_creador:
                creador_nombre = creador_nombre or u_creador.nombre_completo
                if not creador_rol:
                    creador_rol = getattr(getattr(u_creador, "rol_rel", None), "nombre", None) or "CONDUCTOR"

        now = datetime.now()
        solicitud = TallerSolicitud(
            n_bus=n_bus or (dto.n_bus if dto.n_bus else str(bus_id)),
            bus_id=bus_id,
            usuario_creador_id=creador_id,
            estado=EstadoSolicitud.PENDIENTE.value,
            descripcion_general=dto.descripcion_general,
            foto_url=dto.foto_url,
            fecha_creacion=now,
            fecha_actualizacion=now,
            horas_taller_acumuladas=0.0,
        )

        rol_upper = (creador_rol or "").upper().strip()
        debe_marcar_en_taller = False
        if dto.ingreso_inmediato_taller is True:
            debe_marcar_en_taller = True
        elif dto.ingreso_inmediato_taller is None and rol_upper in [
            RolUsuario.SUPERVISOR.value,
            RolUsuario.ADMIN.value,
        ]:
            debe_marcar_en_taller = True

        estadias_a_procesar: List[TallerSolicitudEstadia] = []
        if debe_marcar_en_taller:
            solicitud.fecha_primer_ingreso_taller = now
            solicitud.horas_demora_primer_ingreso = 0.0

            primera_estadia = TallerSolicitudEstadia(
                numero_visita=1,
                fecha_ingreso=now,
            )
            solicitud.estadias.append(primera_estadia)
            estadias_a_procesar.append(primera_estadia)

            if bus_id:
                if not bus_obj:
                    bus_obj = await self.repo.get_bus_by_id(db, bus_id)
                if bus_obj:
                    bus_obj.en_taller = True
                    solicitud.bus = bus_obj
                    logger.info(
                        "[MANTENCION] Bus id=%s marcado en taller (en_taller=True) por %s",
                        bus_id,
                        creador_nombre,
                    )

        evidencias_a_procesar: List[TallerSolicitudEvidencia] = []
        for ev_data in uploaded_evidencias:
            db_path = ev_data.get("path") or ev_data["url"]
            ev_obj = TallerSolicitudEvidencia(
                usuario_id=creador_id,
                url=db_path,
                original_filename=ev_data.get("original_filename"),
                size_bytes=ev_data.get("size_bytes"),
                content_type=ev_data.get("content_type"),
                fecha_creacion=now,
            )
            solicitud.evidencias.append(ev_obj)
            evidencias_a_procesar.append(ev_obj)

        detalles_dtos: List[SolicitudDetalleDTO] = []
        detalles_a_procesar = []
        if dto.detalles:
            check_falla_ids = [
                d.falla_id
                for d in dto.detalles
                if d.falla_id and d.categoria_id and not getattr(d, "falla_nombre", None)
            ]
            existing_fallas_info = (
                await self.repo.get_fallas_info_by_ids(db, check_falla_ids)
                if check_falla_ids
                else {}
            )

            needed_cats = [
                d.categoria_id
                for d in dto.detalles
                if d.categoria_id and (
                    not d.falla_id
                    or (d.falla_id in check_falla_ids and d.falla_id not in existing_fallas_info)
                )
            ]
            fallas_map = (
                await self.repo.find_fallas_activas_by_categorias(db, needed_cats)
                if needed_cats
                else {}
            )

            for det_dto in dto.detalles:
                texto = det_dto.texto_falla
                falla_id = det_dto.falla_id
                cat_id = det_dto.categoria_id
                falla_nombre = det_dto.falla_nombre
                cat_nombre_res = getattr(det_dto, "categoria_nombre", None)

                if falla_id in check_falla_ids and falla_id not in existing_fallas_info:
                    falla_id = None
                    if cat_id in fallas_map:
                        falla_id, falla_nombre, cat_nombre_res = fallas_map[cat_id]

                if cat_id and not falla_id and cat_id in fallas_map:
                    falla_id, f_nom, cat_nom = fallas_map[cat_id]
                    falla_nombre = falla_nombre or f_nom
                    cat_nombre_res = cat_nombre_res or cat_nom

                if not texto and falla_id:
                    texto = falla_nombre or f"Avería #{falla_id}"
                elif not texto and cat_id:
                    texto = f"Avería de categoría #{cat_id}"
                elif not texto:
                    continue

                falla_nombre = falla_nombre or texto

                detalle = TallerSolicitudDetalle(
                    falla_id=falla_id,
                    descripcion_personalizada=texto,
                    resuelto=False,
                    fecha_creacion=now,
                )
                solicitud.detalles.append(detalle)
                detalles_a_procesar.append(
                    (detalle, det_dto, falla_id, cat_id, falla_nombre, cat_nombre_res)
                )

        self.repo.add_solicitud(db, solicitud)
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("[MANTENCION] Error al persistir solicitud: %s", exc)
            raise

        if detalles_a_procesar:
            for (
                detalle,
                det_dto,
                falla_id,
                cat_id,
                falla_nombre,
                cat_nombre_res,
            ) in detalles_a_procesar:
                falla_dto = None
                cat_dto = None
                cat_nom_final = (
                    getattr(det_dto, "categoria_nombre", None)
                    or cat_nombre_res
                    or (f"Categoría #{cat_id}" if cat_id else None)
                )
                if cat_id:
                    cat_dto = CategoriaFallaDTO(
                        id=cat_id,
                        nombre=cat_nom_final or f"Categoría #{cat_id}",
                        is_active=True,
                        falla_id=falla_id,
                        falla_nombre=falla_nombre,
                    )
                if falla_id:
                    falla_nom_final = (
                        getattr(det_dto, "falla_nombre", None)
                        or falla_nombre
                        or det_dto.descripcion_personalizada
                        or f"Avería #{falla_id}"
                    )
                    falla_dto = FallaTallerDTO(
                        id=falla_id,
                        categoria_id=cat_id or 1,
                        nombre=falla_nom_final,
                        is_active=True,
                        categoria=cat_dto,
                    )
                cat_nombre = cat_dto.nombre if cat_dto else None
                detalles_dtos.append(
                    SolicitudDetalleDTO(
                        id=detalle.id,
                        solicitud_id=solicitud.id,
                        categoria_id=cat_id or (falla_dto.categoria_id if falla_dto else 1),
                        categoria_nombre=cat_nombre,
                        falla_id=falla_id,
                        falla=falla_dto,
                        descripcion_personalizada=det_dto.descripcion_personalizada,
                        resuelto=False,
                        falta_repuesto=False,
                        comentario_repuesto=None,
                        fecha_creacion=now,
                        fecha_resolucion=None,
                        mecanico_resolvio_id=None,
                        mecanico_resolvio_nombre=None,
                        mecanicos_asignados=[],
                        historial_asignaciones=[],
                    )
                )

        evidencias_dtos = [
            SolicitudEvidenciaDTO(
                id=ev.id,
                solicitud_id=solicitud.id,
                detalle_id=ev.detalle_id,
                usuario_id=ev.usuario_id,
                url=self.storage.get_url(ev.url) or ev.url,
                original_filename=ev.original_filename,
                size_bytes=ev.size_bytes,
                content_type=ev.content_type,
                fecha_creacion=ev.fecha_creacion,
            )
            for ev in evidencias_a_procesar
        ]

        estadias_dtos = [
            EstadiaTallerDTO(
                id=getattr(e, "id", None),
                solicitud_id=solicitud.id,
                numero_visita=e.numero_visita,
                fecha_ingreso=e.fecha_ingreso,
                fecha_salida=e.fecha_salida,
                horas_estadia=e.horas_estadia,
                motivo_salida=e.motivo_salida,
            )
            for e in estadias_a_procesar
        ]

        return SolicitudDTO(
            id=solicitud.id,
            n_bus=solicitud.n_bus,
            bus_id=solicitud.bus_id,
            bus_patente=bus_patente,
            usuario_creador_id=solicitud.usuario_creador_id,
            usuario_creador_nombre=creador_nombre,
            mecanico_cierre_id=None,
            mecanico_cierre_nombre=None,
            estado=solicitud.estado,
            descripcion_general=solicitud.descripcion_general,
            foto_url=self.storage.get_url(solicitud.foto_url),
            motivo_incompleto_checklist=None,
            motivo_cierre_parcial=None,
            fecha_creacion=solicitud.fecha_creacion,
            fecha_actualizacion=solicitud.fecha_actualizacion or now,
            fecha_cierre=None,
            fecha_liberacion=None,
            fecha_primer_ingreso_taller=solicitud.fecha_primer_ingreso_taller,
            horas_demora_primer_ingreso=solicitud.horas_demora_primer_ingreso,
            horas_taller_acumuladas=0.0,
            total_visitas=len(estadias_dtos),
            horas_en_taller=0.0 if len(estadias_dtos) > 0 else None,
            reincidencias_30d=0,
            pauta_completada=False,
            total_fallas=len(detalles_dtos),
            fallas_resueltas=0,
            fallas_con_falta_repuesto=0,
            fallas_pendientes=len(detalles_dtos),
            detalles=detalles_dtos,
            mecanicos=[],
            historial_mecanicos=[],
            comentarios=[],
            pauta_respuestas=[],
            evidencias=evidencias_dtos,
            estadias=estadias_dtos,
        )


solicitud_service = SolicitudService()
