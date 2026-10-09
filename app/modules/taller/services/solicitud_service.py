import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.storage.storage_service import storage_service, StorageService
from app.modules.taller.constants import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_PAGE_SKIP,
    EstadoSolicitud,
    TipoComentarioBitacora,
    EstadoFalla,
    TipoEventoFalla,
)
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_estadia import TallerSolicitudEstadia
from app.modules.taller.models.taller_solicitud_evidencia import TallerSolicitudEvidencia
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
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
from app.core.realtime.events import RealtimeEvent, publish_event_soon
from app.modules.taller.services.trazabilidad_fallas import registrar_evento_falla

from app.modules.taller.services.trazabilidad_estados import RegistroEstadoOT, registrar_evento_estado

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

    async def get_historial_estados(self, db: AsyncSession, solicitud_id: int, skip: int, limit: int):
        from app.modules.taller.dtos.estado_evento_dto import EstadoEventoDTO
        if not await self.repo.check_solicitud_exists(db, solicitud_id):
            raise NotFoundException("Solicitud de taller no encontrada")
        eventos, total = await self.repo.get_historial_estados(db, solicitud_id, skip, limit)
        return [EstadoEventoDTO.model_validate(evento) for evento in eventos], total

    async def list_pendientes(
        self,
        db: AsyncSession,
        limit: Optional[int] = DEFAULT_PAGE_LIMIT,
        skip: int = DEFAULT_PAGE_SKIP,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
        estado: Optional[str] = None,
    ) -> List[SolicitudResumenDTO]:
        """Pestaña 1 Mecánico: Buses esperando o en atención en taller (PENDIENTE / EN_REPARACION)."""
        logger.debug(
            "[MANTENCION] Listando solicitudes pendientes/en reparación | limit=%s | skip=%s | fecha_desde=%s | fecha_hasta=%s | estado=%s",
            limit,
            skip,
            fecha_desde,
            fecha_hasta,
            estado,
        )
        solicitudes = await self.repo.list_pendientes(
            db, limit=limit, skip=skip, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, estado=estado
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
        estado: Optional[str] = None,
    ) -> int:
        """Retorna el conteo total de solicitudes pendientes o en reparación en taller."""
        return await self.repo.count_pendientes(
            db, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, estado=estado
        )

    async def list_pendientes_con_total(
        self,
        db: AsyncSession,
        limit: Optional[int] = DEFAULT_PAGE_LIMIT,
        skip: int = DEFAULT_PAGE_SKIP,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
        estado: Optional[str] = None,
    ) -> Tuple[List[SolicitudResumenDTO], int]:
        """Entrega la página y su total desde la misma consulta en PostgreSQL.

        ``total_count`` proviene de ``count(*) over()``. Sólo se consulta el
        conteo por separado en el fallback SQLite o si se pidió una página
        fuera de rango, caso que no produce ninguna fila desde la cual leerlo.
        """
        solicitudes = await self.repo.list_pendientes(
            db, limit=limit, skip=skip, fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta, estado=estado,
        )
        if solicitudes and isinstance(solicitudes[0], dict):
            total = int(solicitudes[0].get("total_count") or 0)
        elif solicitudes:
            total = await self.repo.count_pendientes(
                db, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, estado=estado
            )
        elif db.bind and db.bind.dialect.name == "postgresql" and skip:
            total = await self.repo.count_pendientes(
                db, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, estado=estado
            )
        else:
            total = 0

        results = [
            dict_to_solicitud_resumen_dto(s, storage=self.storage)
            if isinstance(s, dict)
            else orm_to_solicitud_resumen_dto(s, storage=self.storage)
            for s in solicitudes
        ]
        return results, total

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

    async def list_mis_trabajos_con_total(
        self,
        db: AsyncSession,
        mecanico_id: int,
        limit: Optional[int] = DEFAULT_PAGE_LIMIT,
        skip: int = DEFAULT_PAGE_SKIP,
        fecha_desde: Optional[datetime] = None,
        fecha_hasta: Optional[datetime] = None,
    ) -> Tuple[List[SolicitudResumenDTO], int]:
        """Entrega Mis trabajos y total sin un COUNT separado en PostgreSQL."""
        solicitudes = await self.repo.list_mis_trabajos(
            db, mecanico_id, limit=limit, skip=skip,
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        )
        if solicitudes and isinstance(solicitudes[0], dict):
            total = int(solicitudes[0].get("total_count") or 0)
        elif solicitudes:
            total = await self.repo.count_mis_trabajos(
                db, mecanico_id=mecanico_id, fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
            )
        elif db.bind and db.bind.dialect.name == "postgresql" and skip:
            total = await self.repo.count_mis_trabajos(
                db, mecanico_id=mecanico_id, fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
            )
        else:
            total = 0

        results = [
            dict_to_solicitud_resumen_dto(
                s, storage=self.storage, mecanico_id=mecanico_id
            )
            if isinstance(s, dict)
            else orm_to_solicitud_resumen_dto(
                s, storage=self.storage, mecanico_id=mecanico_id
            )
            for s in solicitudes
        ]
        return results, total

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
        if archivos_fotos:
            # Las cargas son I/O externo y no deben retener ningún lock de BD.
            # El límite evita saturar GCS/local storage con un multipart grande.
            upload_semaphore = asyncio.Semaphore(4)

            async def _subir_evidencia(archivo: UploadFile) -> dict:
                async with upload_semaphore:
                    return await self.storage.upload_image(
                        file=archivo, folder="solicitudes"
                    )

            uploaded_evidencias = list(
                await asyncio.gather(*(_subir_evidencia(f) for f in archivos_fotos))
            )
        for upload_res in uploaded_evidencias:
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

        if bus_id:
            bus_obj = await self.repo.get_bus_by_id(db, bus_id)
            if not bus_obj:
                raise NotFoundException("El bus indicado no existe")
            if n_bus and bus_obj.n_bus and n_bus.strip().lower() != bus_obj.n_bus.strip().lower():
                raise BusinessRuleException("bus_id y n_bus deben identificar el mismo bus")
            bus_patente = bus_obj.patente
            n_bus = bus_obj.n_bus or n_bus or str(bus_id)
        elif dto.n_bus:
            bus_info = await self.repo.get_bus_info_by_n_bus(db, dto.n_bus)
            if bus_info:
                bus_id, bus_patente = bus_info

        # 2. Creador de la solicitud
        if not creador_nombre or not creador_rol:
            u_creador = await self.repo.get_usuario_by_id(db, creador_id)
            if u_creador:
                creador_nombre = creador_nombre or u_creador.nombre_completo
                if not creador_rol:
                    creador_rol = getattr(getattr(u_creador, "rol_rel", None), "nombre", None) or "CONDUCTOR"

        now = datetime.now(timezone.utc)
        solicitud = await self.repo.get_solicitud_activa_por_bus(db, bus_id, n_bus)
        es_nueva_ot = solicitud is None
        if es_nueva_ot:
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
        else:
            solicitud.fecha_actualizacion = now
            logger.info(
                "[MANTENCION] Nuevas fallas se anexarán a OT activa | solicitud_id=%s | bus_id=%s",
                solicitud.id,
                solicitud.bus_id,
            )

        # Registrar una avería no acredita el ingreso físico del bus, sea cual
        # sea el rol del reportante. El ingreso inmediato debe ser explícito.
        debe_marcar_en_taller = dto.ingreso_inmediato_taller is True

        estadias_a_procesar: List[TallerSolicitudEstadia] = []
        if es_nueva_ot and debe_marcar_en_taller:
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
            if es_nueva_ot:
                solicitud.evidencias.append(ev_obj)
            else:
                ev_obj.solicitud_id = solicitud.id
                self.repo.add_evidencia(db, ev_obj)
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
                    solicitud_id=solicitud.id if not es_nueva_ot else None,
                    falla_id=falla_id,
                    descripcion_personalizada=texto,
                    resuelto=False,
                    fecha_creacion=now,
                    fecha_reporte=now,
                    reportado_por_id=creador_id,
                )
                if es_nueva_ot:
                    solicitud.detalles.append(detalle)
                else:
                    self.repo.add_detalle(db, detalle)
                detalles_a_procesar.append(
                    (detalle, det_dto, falla_id, cat_id, falla_nombre, cat_nombre_res)
                )

        if es_nueva_ot:
            self.repo.add_solicitud(db, solicitud)
        try:
            await self.repo.flush(db)
            for detalle, *_ in detalles_a_procesar:
                registrar_evento_falla(
                    db,
                    self.repo,
                    detalle_id=detalle.id,
                    tipo_evento=TipoEventoFalla.REPORTADA.value,
                    actor_id=creador_id,
                    actor_nombre=creador_nombre,
                    estado_anterior=None,
                    estado_nuevo=EstadoFalla.PENDIENTE.value,
                    fecha_evento=now,
                    comentario=detalle.descripcion_personalizada,
                )
            if not es_nueva_ot:
                descripcion = (dto.descripcion_general or "").strip()
                resumen = f"{creador_nombre or 'Usuario'} reportó {len(detalles_a_procesar)} nueva(s) falla(s)."
                if descripcion:
                    resumen = f"{resumen} Detalle: {descripcion}"
                self.repo.add_comentario(
                    db,
                    TallerSolicitudComentario(
                        solicitud_id=solicitud.id,
                        usuario_id=creador_id,
                        tipo=TipoComentarioBitacora.SISTEMA.value,
                        comentario=resumen,
                        fecha_registro=now,
                    ),
                )
            if es_nueva_ot:
                await registrar_evento_estado(
                    db, RegistroEstadoOT(
                        solicitud_id=solicitud.id, estado_anterior=None,
                        estado_nuevo=solicitud.estado, actor_id=creador_id,
                        actor_nombre=creador_nombre, fecha_evento=now, tipo_evento="CREACION",
                    ),
                )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("[MANTENCION] Error al persistir solicitud: %s", exc)
            raise

        result = await self.get_solicitud(db, solicitud.id)
        publish_event_soon(RealtimeEvent(
            resource_type="work_order",
            resource_id=result.id,
            action="created" if es_nueva_ot else "updated",
            actor_id=creador_id,
            version=result.fecha_actualizacion,
        ))
        return result


solicitud_service = SolicitudService()
