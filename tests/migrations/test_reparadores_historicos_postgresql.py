"""Regresión de los nombres de reparadores en PostgreSQL local desechable."""
from datetime import datetime, timezone

import pytest

from test_buses_mecanicos_postgresql import sesiones_postgres
from test_motivo_salida_estadia import postgres_temporal
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_falla_evento import TallerFallaEvento
from app.modules.taller.models.taller_falla_evento_mecanico import TallerFallaEventoMecanico
from app.modules.taller.repository.taller_repository import TallerRepository
from app.modules.taller.services.mappers import dict_to_solicitud_dto, orm_to_solicitud_dto


@pytest.mark.parametrize("caso", ["directo", "asignaciones", "evento", "reabierta"])
async def test_nombre_reparador_en_consulta_sql_y_orm(sesiones_postgres, caso):
    # Arrange: evento antiguo sin autores y reparador conservado en la falla.
    fecha = datetime(2026, 10, 1, tzinfo=timezone.utc)
    async with sesiones_postgres() as db:
        rol = Rol(nombre="MECANICO")
        db.add(rol)
        await db.flush()
        usuarios = [Usuario(nombre=nombre, apellido=apellido, username=nombre,
                            password_hash="test", rol_id=rol.id)
                    for nombre, apellido in [("Cecil", "Iturrieta"), ("Juan", "Ferrada")]]
        db.add_all(usuarios)
        await db.flush()
        solicitud = TallerSolicitud(n_bus="407", estado="LIBERADO", es_ot=True)
        db.add(solicitud)
        await db.flush()
        detalle = TallerSolicitudDetalle(solicitud_id=solicitud.id, estado="RESUELTA",
                                         resuelto=True, mecanico_resolvio_id=usuarios[0].id)
        db.add(detalle)
        await db.flush()
        evento = TallerFallaEvento(detalle_id=detalle.id, tipo_evento="RESUELTA",
                                   estado_nuevo="RESUELTA", actor_nombre_snapshot="No registrado",
                                   fecha_evento=fecha)
        db.add(evento)
        await db.flush()
        if caso in ("asignaciones", "evento"):
            db.add_all([TallerAsignacionFalla(solicitud_id=solicitud.id, detalle_id=detalle.id,
                        mecanico_id=u.id, is_activo=False, resuelto_en_esta_asignacion=True)
                        for u in usuarios])
        if caso == "evento":
            # Un evento con autores conserva su equipo, aunque las asignaciones difieran.
            db.add(TallerFallaEventoMecanico(evento_id=evento.id, mecanico_id=usuarios[1].id,
                                            mecanico_nombre_snapshot="Juan Ferrada"))
        if caso == "reabierta":
            detalle.estado, detalle.resuelto = "PENDIENTE", False
            db.add(TallerFallaEvento(detalle_id=detalle.id, tipo_evento="REABIERTA",
                   estado_nuevo="PENDIENTE", actor_nombre_snapshot="Supervisor", fecha_evento=fecha))
        await db.commit()
        solicitud_id = solicitud.id

    # Act: consulta de producción y ruta ORM con sesiones nuevas.
    async with sesiones_postgres() as db:
        fila = await TallerRepository().get_solicitud_dto_by_id(db, solicitud_id)
        sql = dict_to_solicitud_dto(fila).detalles[0]
    async with sesiones_postgres() as db:
        entidad = await TallerRepository().get_solicitud_by_id(db, solicitud_id)
        orm = orm_to_solicitud_dto(entidad).detalles[0]

    # Assert: nombre y equipo coherentes; una reapertura no muestra reparadores previos.
    esperados = {"directo": {"Cecil Iturrieta"},
                 "asignaciones": {"Cecil Iturrieta", "Juan Ferrada"},
                 "evento": {"Juan Ferrada"}, "reabierta": set()}[caso]
    for resultado in (sql, orm):
        assert {m.nombre for m in resultado.mecanicos_resolvieron} == esperados
        assert set((resultado.mecanico_resolvio_nombre or "").split(", ")) - {""} == esperados
        assert resultado.historial_eventos[0].actor_nombre == "No registrado"
        if caso != "evento":
            assert resultado.historial_eventos[0].mecanicos_resolvieron == []
