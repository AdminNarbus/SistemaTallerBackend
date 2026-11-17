"""Catálogo y trazabilidad de repuestos utilizados en fallas."""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import BusinessRuleException, ConflictException, NotFoundException, PermissionException
from app.core.realtime.events import RealtimeEvent, publish_event_soon
from app.modules.taller.dtos.repuesto_dto import RepuestoUtilizadoDTO
from app.modules.taller.models.repuesto import Repuesto
from app.modules.taller.models.taller_repuesto_utilizado import TallerRepuestoUtilizado
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_ubicacion import OperacionResultado
from app.modules.taller.repository.repuesto_repository import repuesto_repository
from app.modules.taller.repository.taller_repository import taller_repository
from app.modules.taller.utils import describir_detalle_averia


class RepuestoService:
    async def listar_catalogo(self, db, actor, q, incluir_inactivos, skip, limit):
        if incluir_inactivos and actor.rol.upper() == "MECANICO":
            raise PermissionException("Solo supervisión puede consultar artículos inactivos")
        return await repuesto_repository.listar_catalogo(db, q, incluir_inactivos, skip, limit)

    async def guardar_catalogo(self, db, dto, repuesto_id=None):
        datos = dto.model_dump(exclude_unset=repuesto_id is not None)
        for campo in ("codigo", "nombre"):
            if campo in datos:
                if datos[campo] is None or not datos[campo].strip():
                    raise BusinessRuleException(f"{campo} es obligatorio")
                datos[campo] = datos[campo].strip()
        if datos.get("is_active", True) is None:
            raise BusinessRuleException("is_active no puede ser nulo")
        articulo = await db.get(Repuesto, repuesto_id) if repuesto_id is not None else Repuesto()
        if articulo is None:
            raise NotFoundException("Repuesto no encontrado")
        for campo, valor in datos.items():
            setattr(articulo, campo, valor)
        db.add(articulo)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictException("El código del repuesto ya existe") from exc
        await db.refresh(articulo)
        return articulo

    async def _contexto(self, db, solicitud_id, detalle_id=None, bloquear=False):
        if bloquear:
            await taller_repository.lock_solicitud_estado(db, solicitud_id)
        ot = await db.get(TallerSolicitud, solicitud_id)
        if not ot:
            raise NotFoundException("OT no encontrada")
        detalle = None
        if detalle_id is not None:
            detalle = await taller_repository.get_detalle_operacional(db, solicitud_id, detalle_id)
            if not detalle:
                raise NotFoundException("Falla no encontrada en esta OT")
        return ot, detalle

    async def _autorizar(self, db, actor, ot, detalle):
        if not ot.es_ot or ot.estado == "FINALIZADO":
            raise BusinessRuleException("La OT debe estar aprobada y abierta")
        from app.modules.taller.services.revision_falla_service import exigir_falla_aprobada
        exigir_falla_aprobada(detalle)
        if actor.rol.upper() == "MECANICO":
            asignaciones = await taller_repository.get_asignaciones_activas(db, solicitud_id=ot.id, detalles_ids=[detalle.id])
            if not any(a.mecanico_id == actor.id for a in asignaciones):
                raise PermissionException("Debe estar asignado a esta falla")

    async def _verificar_actor(self, db, actor):
        usuario = await taller_repository.get_usuario_by_id(db, actor.id)
        if not usuario or not usuario.is_active:
            raise PermissionException("Usuario inactivo")
        rol = (getattr(getattr(usuario, "rol_rel", None), "nombre", None) or "").upper().strip()
        if rol not in ("MECANICO", "SUPERVISOR", "ADMIN") or rol != actor.rol.upper().strip():
            raise PermissionException("El rol de la sesión no autoriza esta operación")

    def _salida(self, registro, ot):
        datos = {
            campo: getattr(registro, campo) for campo in RepuestoUtilizadoDTO.model_fields
            if campo not in {"solicitud_id", "bus_id", "n_bus"}
        }
        return RepuestoUtilizadoDTO(**datos, solicitud_id=ot.id, bus_id=ot.bus_id, n_bus=ot.n_bus)

    async def listar_usos(self, db, solicitud_id, detalle_id, incluir_anulados, skip, limit):
        ot, _ = await self._contexto(db, solicitud_id, detalle_id)
        filas, total = await repuesto_repository.listar_usos(db, solicitud_id, detalle_id, incluir_anulados, skip, limit)
        return [self._salida(fila, ot) for fila in filas], total

    async def _replay(self, db, dto, actor, detalle_id, accion, extra):
        huella = hashlib.sha256(json.dumps({"dto": dto.model_dump(mode="json"), "extra": extra}, sort_keys=True).encode()).hexdigest()
        previo = await db.get(OperacionResultado, str(dto.operacion_id))
        if previo:
            if (previo.actor_id, previo.detalle_id, previo.accion, previo.huella) != (actor.id, detalle_id, accion, huella):
                raise ConflictException("operacion_id ya fue usado con otro contenido")
            return huella, RepuestoUtilizadoDTO.model_validate(previo.respuesta)
        return huella, None

    async def _guardar(self, db, ot, detalle, actor, dto, accion, huella, registro, texto=None):
        version = datetime.now(timezone.utc) if texto else None
        try:
            await db.flush()
            salida = self._salida(registro, ot)
            db.add(OperacionResultado(operacion_id=str(dto.operacion_id), actor_id=actor.id, detalle_id=detalle.id, accion=accion, huella=huella, respuesta=salida.model_dump(mode="json")))
            if texto:
                db.add(TallerSolicitudComentario(solicitud_id=ot.id, usuario_id=actor.id, tipo="GENERAL", comentario=texto))
                await taller_repository.touch_fecha_actualizacion(db, ot.id, version)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictException("La operación o el repuesto ya fue registrado") from exc
        if texto:
            publish_event_soon(RealtimeEvent(resource_type="work_order", resource_id=ot.id, action=accion, actor_id=actor.id, version=version))
        return salida

    async def registrar(self, db, solicitud_id, detalle_id, dto, actor):
        ot, detalle = await self._contexto(db, solicitud_id, detalle_id, bloquear=True)
        await self._verificar_actor(db, actor)
        huella, previo = await self._replay(db, dto, actor, detalle_id, "REPUESTO_ALTA", solicitud_id)
        if previo:
            return previo, False
        await self._autorizar(db, actor, ot, detalle)
        articulo = await db.get(Repuesto, dto.repuesto_id)
        if not articulo or not articulo.is_active:
            raise NotFoundException("Repuesto activo no encontrado")
        existente = await repuesto_repository.uso_vigente(db, detalle_id, articulo.id)
        if existente and existente.cantidad_utilizada != dto.cantidad:
            raise ConflictException("Anule el registro antes de corregir la cantidad")
        if existente:
            return await self._guardar(db, ot, detalle, actor, dto, "REPUESTO_ALTA", huella, existente), False
        registro = TallerRepuestoUtilizado(falla_detalle_id=detalle_id, repuesto_id=articulo.id, cantidad_utilizada=dto.cantidad, unidad_al_registrar=articulo.unidad, usuario_registro_id=actor.id, nombre_usuario_al_registrar=actor.nombre_completo, codigo_repuesto_al_registrar=articulo.codigo, nombre_repuesto_al_registrar=articulo.nombre, parte_repuesto_al_registrar=articulo.parte)
        db.add(registro)
        texto = f"Repuesto utilizado en '{describir_detalle_averia(detalle)}': [{articulo.codigo}] {articulo.nombre}; cantidad: {dto.cantidad}."
        return await self._guardar(db, ot, detalle, actor, dto, "REPUESTO_ALTA", huella, registro, texto), True

    async def anular(self, db, solicitud_id, detalle_id, registro_id, dto, actor):
        ot, detalle = await self._contexto(db, solicitud_id, detalle_id, bloquear=True)
        await self._verificar_actor(db, actor)
        huella, previo = await self._replay(db, dto, actor, detalle_id, "REPUESTO_ANULACION", [solicitud_id, registro_id])
        if previo:
            return previo
        await self._autorizar(db, actor, ot, detalle)
        registro = await db.get(TallerRepuestoUtilizado, registro_id)
        if not registro or registro.falla_detalle_id != detalle_id:
            raise NotFoundException("Registro de repuesto no encontrado")
        if actor.rol.upper() == "MECANICO" and registro.usuario_registro_id != actor.id:
            raise PermissionException("Solo puede anular sus propios registros")
        if not dto.motivo.strip():
            raise BusinessRuleException("Debe indicar un motivo")
        texto = None
        if registro.fecha_anulacion is None:
            registro.fecha_anulacion = datetime.now(timezone.utc)
            registro.usuario_anulacion_id = actor.id
            registro.nombre_usuario_al_anular = actor.nombre_completo
            registro.motivo_anulacion = dto.motivo.strip()
            texto = f"Registro de repuesto anulado en '{describir_detalle_averia(detalle)}': [{registro.codigo_repuesto_al_registrar}] {registro.nombre_repuesto_al_registrar}; cantidad: {registro.cantidad_utilizada}."
        return await self._guardar(db, ot, detalle, actor, dto, "REPUESTO_ANULACION", huella, registro, texto)


repuesto_service = RepuestoService()
