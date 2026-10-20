"""Registra resultados y ubicación de reparación en una transacción por falla."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, ConflictException, NotFoundException, PermissionException
from app.modules.taller.constants import EstadoFalla, TipoEventoFalla
from app.modules.taller.dtos.averias_dto import CheckFallaDTO, DetalleUpdateDTO, MecanicoResumenDTO
from app.modules.taller.dtos.taller_ubicacion_dto import UbicacionEventoDTO, TallerSnapshotDTO
from app.modules.taller.dtos.taller_ubicacion_dto import CorregirUbicacionDTO
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_falla_evento import TallerFallaEvento
from app.modules.taller.models.taller_falla_evento_mecanico import TallerFallaEventoMecanico
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_ubicacion import (
    Ciudad, OperacionResultado, Taller, TallerResultadoColaborador, TallerResultadoUbicacion,
)
from app.modules.taller.repository.taller_repository import taller_repository
from app.modules.taller.services.bitacora_adjuntos import guardar_adjuntos_bitacora
from app.modules.taller.services.bitacora_textos import agregar_texto, formatear_reparacion
from app.modules.taller.services.trazabilidad_fallas import registrar_evento_falla
from app.modules.taller.utils import describir_detalle_averia, calcular_duracion_minutos


class ResultadoFallaService:
    async def corregir_ubicacion(self, db: AsyncSession, solicitud_id: int, detalle_id: int,
                                 evento_id: int, actor_id: int, actor_nombre: str,
                                 actor_rol: str, dto: CorregirUbicacionDTO) -> UbicacionEventoDTO:
        if actor_rol not in ("SUPERVISOR", "ADMIN"):
            raise PermissionException("Solo supervisión puede corregir ubicación histórica")
        await taller_repository.lock_solicitud_estado(db, solicitud_id)
        detalle = await taller_repository.get_detalle_operacional(db, solicitud_id, detalle_id)
        if detalle is None:
            raise NotFoundException("Detalle de falla no encontrado en esta OT")
        evento = await db.get(TallerFallaEvento, evento_id)
        if evento is None or evento.detalle_id != detalle_id:
            raise NotFoundException("El evento no pertenece a esta falla")
        huella = hashlib.sha256(json.dumps(
            {"evento_id": evento_id, "payload": dto.model_dump(mode="json")}, sort_keys=True
        ).encode()).hexdigest()
        previa = await db.get(OperacionResultado, str(dto.operacion_id))
        if previa:
            if (previa.actor_id, previa.detalle_id, previa.accion, previa.huella) != (actor_id, detalle_id, "UBICACION", huella):
                raise ConflictException("operacion_id ya fue usado con otro contenido")
            return UbicacionEventoDTO.model_validate(previa.respuesta)
        if evento.tipo_evento not in ("RESUELTA", "INCOMPLETA"):
            raise BusinessRuleException("Solo se puede ubicar un resultado RESUELTA o INCOMPLETA")
        if await db.scalar(select(TallerSolicitud.id).where(TallerSolicitud.id == solicitud_id)) is None:
            raise NotFoundException("OT no encontrada")
        latest = await db.scalar(select(TallerResultadoUbicacion).where(
            TallerResultadoUbicacion.evento_id == evento_id
        ).order_by(TallerResultadoUbicacion.version.desc()).limit(1))
        if (latest.id if latest else None) != dto.ubicacion_esperada_id:
            raise ConflictException("La ubicación cambió; recargue la historia de la falla")
        ids = [dto.taller_id, *dto.talleres_colaboradores_ids]
        if len(ids) != len(set(ids)):
            raise BusinessRuleException("No repita el taller responsable como colaborador")
        talleres = list((await db.scalars(select(Taller).where(Taller.id.in_(ids)).order_by(Taller.id))).all())
        if len(talleres) != len(ids):
            raise NotFoundException("Uno o más talleres no existen")
        por_id = {t.id: t for t in talleres}
        nueva = self._guardar_ubicacion(db, evento_id, (latest.version + 1) if latest else 1,
            por_id[dto.taller_id], [por_id[i] for i in dto.talleres_colaboradores_ids],
            actor_id, actor_nombre, str(dto.operacion_id), dto.motivo)
        await db.flush()
        salida = self._ubicacion_dto(nueva)
        db.add(OperacionResultado(operacion_id=str(dto.operacion_id), actor_id=actor_id,
            accion="UBICACION", detalle_id=detalle_id, huella=huella,
            respuesta=salida.model_dump(mode="json")))
        await taller_repository.touch_fecha_actualizacion(db, solicitud_id)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictException("Conflicto al guardar la ubicación") from exc
        return salida

    async def registrar(self, db: AsyncSession, solicitud_id: int, detalle_id: int, actor_id: int,
                        actor_nombre: Optional[str], actor_rol: str, dto: CheckFallaDTO,
                        fotos: Optional[list[UploadFile]] = None) -> DetalleUpdateDTO:
        self._validar_uuid_y_snapshot(dto)
        await taller_repository.lock_solicitud_estado(db, solicitud_id)
        actor = await taller_repository.get_usuario_by_id(db, actor_id)
        if actor is None or not actor.is_active:
            raise PermissionException("El usuario no está activo")
        rol = (getattr(actor, "rol", "") or "").upper()
        if actor_rol and actor_rol.upper() != rol:
            raise PermissionException("El rol de la sesión no coincide con el usuario")
        detalle = await taller_repository.get_detalle_operacional(db, solicitud_id, detalle_id)
        if detalle is None:
            raise NotFoundException("Detalle de falla no encontrado")
        solicitud_estado = await db.scalar(select(TallerSolicitud.estado).where(TallerSolicitud.id == solicitud_id))
        if solicitud_estado is None:
            raise NotFoundException("Solicitud de taller no encontrada")

        huella = await self._huella(dto, fotos)
        previa = await db.get(OperacionResultado, str(dto.operacion_id))
        if previa:
            return self._replay(previa, actor_id, detalle_id, huella)
        if solicitud_estado == "FINALIZADO":
            raise BusinessRuleException("Reabra la OT antes de registrar un resultado")
        evento_vigente_id = await db.scalar(
            select(TallerFallaEvento.id).where(TallerFallaEvento.detalle_id == detalle_id)
            .order_by(TallerFallaEvento.id.desc()).limit(1)
        )
        if evento_vigente_id != dto.evento_esperado_id:
            raise ConflictException("La falla cambió desde que se cargó; recargue la OT")

        ahora = datetime.now(timezone.utc)
        target = dto.effective_estado.value
        anterior = detalle.estado
        if target == "PENDIENTE":
            if dto.taller_id is not None or dto.talleres_colaboradores_ids:
                raise BusinessRuleException("La reapertura no admite taller ni colaboradores")
            if dto.effective_mecanicos_ids:
                raise BusinessRuleException("La reapertura no admite autores")
        else:
            if dto.taller_id is None:
                raise BusinessRuleException("Debe indicar el taller responsable")
            if target == "RESUELTA" and anterior == target and rol == "MECANICO":
                raise PermissionException("Solo supervisión puede registrar otra RESUELTA")
            if target == "INCOMPLETA" and rol == "MECANICO" and anterior != target:
                pass
            elif target == anterior and not (target == "INCOMPLETA" or (target == "RESUELTA" and rol in ("SUPERVISOR", "ADMIN"))):
                raise BusinessRuleException("Ese estado no admite un resultado sucesivo")
            if rol == "MECANICO" and dto.fecha_cambio_estado is not None:
                raise PermissionException("El mecánico registra con la hora del servidor")

        fecha = ahora
        if dto.fecha_cambio_estado is not None:
            if rol not in ("SUPERVISOR", "ADMIN"):
                raise PermissionException("Solo supervisión puede indicar fecha efectiva")
            fecha = dto.fecha_cambio_estado.astimezone(timezone.utc)
            if fecha > ahora:
                raise BusinessRuleException("La fecha efectiva no puede ser futura")

        asignaciones = await taller_repository.get_asignaciones_activas(
            db, solicitud_id=solicitud_id, detalles_ids=[detalle_id]
        )
        if rol == "MECANICO" and not any(a.mecanico_id == actor_id for a in asignaciones):
            raise PermissionException("Debe tener una asignación activa en esta falla")
        if rol not in ("MECANICO", "SUPERVISOR", "ADMIN"):
            raise PermissionException("Rol no autorizado para registrar resultados")

        autores = await self._resolver_autores(db, dto, rol, actor_id, asignaciones, target)
        taller = None
        colaboradores = []
        if target != "PENDIENTE":
            taller, colaboradores = await self._talleres_resultado(db, dto.taller_id, dto.talleres_colaboradores_ids)
            if not autores and taller.tipo != "EXTERNO" and all(t.tipo != "EXTERNO" for t in colaboradores):
                raise BusinessRuleException("Debe declarar autores o incluir un taller externo")

        if rol in ("SUPERVISOR", "ADMIN") and target != "PENDIENTE" and asignaciones:
            self._reemplazar_equipo(db, asignaciones, autores, solicitud_id, detalle_id, actor_id, ahora)

        detalle.estado = target
        detalle.resuelto = target == "RESUELTA"
        detalle.fecha_cambio_estado = fecha
        fecha_creacion = detalle.fecha_creacion
        if fecha_creacion.tzinfo is None:
            fecha_creacion = fecha_creacion.replace(tzinfo=timezone.utc)
        detalle.fecha_resolucion = fecha if target == "RESUELTA" and fecha >= fecha_creacion else None
        detalle.motivo_incompleto = (dto.motivo_incompleto or dto.comentario or "").strip() or None if target == "INCOMPLETA" else None
        detalle.mecanico_resolvio_id = autores[0].id if target == "RESUELTA" and autores else None
        detalle.falta_repuesto = False if target == "RESUELTA" else detalle.falta_repuesto

        tipo = {"RESUELTA": TipoEventoFalla.RESUELTA.value,
                "INCOMPLETA": TipoEventoFalla.INCOMPLETA.value,
                "PENDIENTE": TipoEventoFalla.REABIERTA.value}[target]
        evento = registrar_evento_falla(
            db, taller_repository, detalle_id=detalle_id, tipo_evento=tipo,
            actor_id=actor_id, actor_nombre=actor_nombre or actor.nombre_completo,
            estado_anterior=anterior, estado_nuevo=target, fecha_evento=fecha,
            comentario=dto.comentario or detalle.motivo_incompleto,
            mecanicos_resolutores=autores,
        )
        await db.flush()
        ubicacion = None
        if taller is not None:
            ubicacion = self._guardar_ubicacion(db, evento.id, 1, taller, colaboradores,
                actor_id, actor_nombre or actor.nombre_completo, str(dto.operacion_id), None)

        nombre_falla = describir_detalle_averia(detalle)
        nombres = [u.nombre_completo for u in autores]
        tipo_comentario = "RESOLUCION" if target == "RESUELTA" else "AVANCE" if target == "INCOMPLETA" else "REAPERTURA"
        texto = (formatear_reparacion(nombre_falla, nombres) if target == "RESUELTA"
                 else agregar_texto(f"Incompleta: {nombre_falla}", detalle.motivo_incompleto) if target == "INCOMPLETA"
                 else f"Reapertura: {nombre_falla}")
        if dto.comentario and dto.comentario.strip() and dto.comentario.strip() not in texto:
            texto = agregar_texto(texto, dto.comentario.strip())
        comentario = TallerSolicitudComentario(
            solicitud_id=solicitud_id, usuario_id=actor_id, tipo=tipo_comentario,
            comentario=texto, fecha_registro=ahora, fecha_evento=fecha,
        )
        db.add(comentario)
        await taller_repository.touch_fecha_actualizacion(db, solicitud_id, ahora)
        await guardar_adjuntos_bitacora(db, comentario=comentario, solicitud_id=solicitud_id,
            detalle_id=detalle_id, usuario_id=actor_id, fotos=fotos)

        respuesta = DetalleUpdateDTO(
            detalle_id=detalle_id, solicitud_id=solicitud_id, estado=target,
            motivo_incompleto=detalle.motivo_incompleto, resuelto=detalle.resuelto,
            falta_repuesto=detalle.falta_repuesto, mecanico_resolvio_id=detalle.mecanico_resolvio_id,
            mecanico_resolvio_nombre=", ".join(nombres) if target == "RESUELTA" and nombres else None,
            mecanicos_resolvieron=[MecanicoResumenDTO(id=u.id, nombre=u.nombre_completo) for u in autores] if target == "RESUELTA" else [],
            mecanicos_avance=[MecanicoResumenDTO(id=u.id, nombre=u.nombre_completo) for u in autores] if target == "INCOMPLETA" else [],
            comentario_repuesto=detalle.comentario_repuesto,
            fecha_resolucion=fecha if target == "RESUELTA" else None,
            fecha_cambio_estado=fecha, fecha_registro=evento.fecha_registro, evento_estado_vigente_id=evento.id,
            ubicacion=self._ubicacion_dto(ubicacion), operacion_id=str(dto.operacion_id), evento_id=evento.id,
        )
        recibo = OperacionResultado(operacion_id=str(dto.operacion_id), actor_id=actor_id,
            accion=target, detalle_id=detalle_id, huella=huella,
            respuesta=respuesta.model_dump(mode="json"))
        db.add(recibo)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictException("La falla cambió o la operación ya fue registrada") from exc
        return respuesta

    def _validar_uuid_y_snapshot(self, dto: CheckFallaDTO):
        if dto.operacion_id is None:
            raise BusinessRuleException("operacion_id es obligatorio")
        if "evento_esperado_id" not in dto.model_fields_set:
            raise BusinessRuleException("evento_esperado_id es obligatorio; puede ser null")

    async def _huella(self, dto: CheckFallaDTO, fotos: Optional[list[UploadFile]]) -> str:
        contenido = json.dumps(dto.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(contenido.encode())
        for archivo in fotos or []:
            data = await archivo.read()
            await archivo.seek(0)
            digest.update((archivo.filename or "").encode())
            digest.update((archivo.content_type or "").encode())
            digest.update(data)
        return digest.hexdigest()

    def _replay(self, operacion: OperacionResultado, actor_id: int, detalle_id: int, huella: str):
        if (operacion.actor_id, operacion.detalle_id, operacion.huella) != (actor_id, detalle_id, huella):
            raise ConflictException("operacion_id ya fue usado con otro actor, recurso o contenido")
        return DetalleUpdateDTO.model_validate(operacion.respuesta)

    async def _resolver_autores(self, db, dto, rol, actor_id, asignaciones, estado):
        if estado == "PENDIENTE":
            if dto.mecanicos_ids:
                raise BusinessRuleException("La reapertura no admite autores")
            return []
        ids = dto.effective_mecanicos_ids
        if rol in ("SUPERVISOR", "ADMIN") and dto.mecanicos_ids is None:
            raise BusinessRuleException("Supervisión debe indicar mecanicos_ids explícitamente")
        if rol == "MECANICO":
            equipo = list(dict.fromkeys(a.mecanico_id for a in asignaciones))
            if ids and set(ids) != set(equipo):
                raise PermissionException("El mecánico solo puede declarar a su equipo activo completo")
            ids = equipo
        if len(ids) != len(set(ids)):
            raise BusinessRuleException("No repita mecánicos en mecanicos_ids")
        usuarios = []
        for mecanico_id in ids:
            usuario = await taller_repository.get_usuario_by_id(db, mecanico_id)
            if usuario is None or not usuario.is_active or usuario.rol != "MECANICO":
                raise BusinessRuleException(f"El usuario {mecanico_id} no es un mecánico activo")
            usuarios.append(usuario)
        return usuarios

    async def _talleres_resultado(self, db, responsable_id, colaboradores_ids):
        if responsable_id in colaboradores_ids or len(colaboradores_ids) != len(set(colaboradores_ids)):
            raise BusinessRuleException("El responsable no puede repetirse como colaborador")
        ids = [responsable_id, *colaboradores_ids]
        talleres = list((await db.scalars(select(Taller).join(Ciudad).where(Taller.id.in_(ids)).order_by(Taller.id))).all())
        if len(talleres) != len(ids):
            raise NotFoundException("Uno o más talleres no existen")
        por_id = {t.id: t for t in talleres}
        if any(not t.is_activo for t in talleres):
            raise BusinessRuleException("Los resultados nuevos requieren talleres activos")
        return por_id[responsable_id], [por_id[i] for i in colaboradores_ids]

    def _reemplazar_equipo(self, db, asignaciones, autores, solicitud_id, detalle_id, actor_id, ahora):
        ids_autores = {u.id for u in autores}
        actuales = {a.mecanico_id: a for a in asignaciones}
        for mecanico_id, asignacion in actuales.items():
            if mecanico_id not in ids_autores:
                asignacion.is_activo = False
                asignacion.fecha_desasignacion = ahora
                asignacion.duracion_minutos = calcular_duracion_minutos(asignacion.fecha_asignacion, ahora)
                asignacion.resuelto_en_esta_asignacion = False
        for autor in autores:
            if autor.id not in actuales:
                asignacion = TallerAsignacionFalla(
                    solicitud_id=solicitud_id, detalle_id=detalle_id, mecanico_id=autor.id,
                    asignado_por_id=actor_id, origen="SUPERVISOR", is_activo=True,
                    fecha_asignacion=ahora, resuelto_en_esta_asignacion=False,
                )
                asignacion.mecanico = autor
                db.add(asignacion)

    def _guardar_ubicacion(self, db, evento_id, version, taller, colaboradores, actor_id, actor_nombre, operacion_id, motivo):
        ubicacion = TallerResultadoUbicacion(
            evento_id=evento_id, version=version, taller_id=taller.id,
            taller_nombre_snapshot=taller.nombre, taller_tipo_snapshot=taller.tipo,
            ciudad_id_snapshot=taller.ciudad_id, ciudad_nombre_snapshot=taller.ciudad.nombre, actor_id=actor_id,
            actor_nombre_snapshot=actor_nombre, operacion_id=operacion_id, motivo=motivo,
        )
        ubicacion.colaboradores = [TallerResultadoColaborador(
                taller_id=colaborador.id, taller_nombre_snapshot=colaborador.nombre,
                taller_tipo_snapshot=colaborador.tipo, ciudad_id_snapshot=colaborador.ciudad_id,
                ciudad_nombre_snapshot=colaborador.ciudad.nombre,
            ) for colaborador in colaboradores]
        db.add(ubicacion)
        return ubicacion

    def _ubicacion_dto(self, ubicacion):
        if ubicacion is None:
            return None
        return UbicacionEventoDTO(
            id=ubicacion.id,
            version=ubicacion.version,
            taller_responsable=TallerSnapshotDTO(id=ubicacion.taller_id, nombre=ubicacion.taller_nombre_snapshot,
                ciudad=ubicacion.ciudad_nombre_snapshot, tipo=ubicacion.taller_tipo_snapshot),
            talleres_colaboradores=[TallerSnapshotDTO(id=t.taller_id, nombre=t.taller_nombre_snapshot,
                ciudad=t.ciudad_nombre_snapshot, tipo=t.taller_tipo_snapshot) for t in ubicacion.colaboradores],
            registrado_por=ubicacion.actor_nombre_snapshot, registrado_por_id=ubicacion.actor_id,
            registrado_en=ubicacion.registrado_en.isoformat() if ubicacion.registrado_en else None,
            operacion_id=ubicacion.operacion_id,
            motivo=ubicacion.motivo,
        )


resultado_falla_service = ResultadoFallaService()
