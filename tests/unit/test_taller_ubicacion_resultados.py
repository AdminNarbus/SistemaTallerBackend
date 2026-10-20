from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ConflictException, PermissionException
from app.modules.taller.constants import EstadoFalla
from app.modules.taller.dtos import CheckFallaDTO, SolicitudCreateDTO, SolicitudDetalleCreateDTO
from app.modules.taller.dtos.taller_ubicacion_dto import CorregirUbicacionDTO
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_falla_evento import TallerFallaEvento
from app.modules.taller.models.taller_falla_evento_mecanico import TallerFallaEventoMecanico
from app.modules.taller.models.taller_ubicacion import Ciudad, Taller, TallerResultadoUbicacion
from app.modules.taller.services.resultado_falla_service import resultado_falla_service
from app.modules.taller.services.taller_service import taller_service
from app.modules.supervision.repository.supervision_repository import supervision_repository


async def _crear_solicitud(db, conductor, falla, sufijo):
    solicitud = await taller_service.create_solicitud(
        db,
        SolicitudCreateDTO(
            n_bus=f"UBICACION-{sufijo}",
            descripcion_general="Prueba de resultado con ubicación",
            detalles=[SolicitudDetalleCreateDTO(falla_id=falla.id)],
        ),
        conductor.id,
    )
    return solicitud, solicitud.detalles[0].id


async def _crear_talleres(db):
    ciudad = Ciudad(codigo="TEST", nombre="Ciudad Test")
    db.add(ciudad)
    await db.flush()
    interno = Taller(nombre="Taller Interno", ciudad_id=ciudad.id, tipo="INTERNO", is_activo=True)
    externo = Taller(nombre="Taller Externo", ciudad_id=ciudad.id, tipo="EXTERNO", is_activo=True)
    db.add_all([interno, externo])
    await db.flush()
    return interno, externo


@pytest.mark.asyncio
async def test_supervision_reemplaza_equipo_y_replay_no_duplica(db_session, seed_test_data):
    conductor = seed_test_data["conductor"]
    a, b = seed_test_data["mecanico1"], seed_test_data["mecanico2"]
    # El tercer autor debe ser mecánico activo; se usa mecánico2 como B y se crea C.
    from app.modules.auth.models.usuario import Usuario
    from app.core.security import get_password_hash
    rol_mecanico = await db_session.scalar(select(Usuario.rol_id).where(Usuario.id == b.id))
    mecanico_c = Usuario(
        nombre="Camila", apellido="Mecanica", username="mecanica-c@narbus.cl",
        password_hash=get_password_hash("password123"), rol_id=rol_mecanico, is_active=True,
    )
    db_session.add(mecanico_c)
    await db_session.flush()
    solicitud, detalle_id = await _crear_solicitud(db_session, conductor, seed_test_data["falla1"], "ABC")
    taller, _ = await _crear_talleres(db_session)
    db_session.add_all([
        TallerAsignacionFalla(solicitud_id=solicitud.id, detalle_id=detalle_id, mecanico_id=a.id,
            asignado_por_id=seed_test_data["supervisor"].id, origen="SUPERVISOR", is_activo=True),
        TallerAsignacionFalla(solicitud_id=solicitud.id, detalle_id=detalle_id, mecanico_id=b.id,
            asignado_por_id=seed_test_data["supervisor"].id, origen="SUPERVISOR", is_activo=True),
    ])
    await db_session.flush()
    esperado = await db_session.scalar(select(TallerFallaEvento.id).where(
        TallerFallaEvento.detalle_id == detalle_id
    ).order_by(TallerFallaEvento.id.desc()).limit(1))
    dto = CheckFallaDTO(
        operacion_id=uuid4(), evento_esperado_id=esperado, estado=EstadoFalla.INCOMPLETA,
        mecanicos_ids=[b.id, mecanico_c.id], taller_id=taller.id,
        motivo_incompleto="Pendiente revisión final",
    )
    primera = await resultado_falla_service.registrar(
        db_session, solicitud.id, detalle_id, seed_test_data["supervisor"].id,
        seed_test_data["supervisor"].nombre_completo, "SUPERVISOR", dto,
    )
    segunda = await resultado_falla_service.registrar(
        db_session, solicitud.id, detalle_id, seed_test_data["supervisor"].id,
        seed_test_data["supervisor"].nombre_completo, "SUPERVISOR", dto,
    )
    with pytest.raises(ConflictException):
        await resultado_falla_service.registrar(
            db_session, solicitud.id, detalle_id, seed_test_data["supervisor"].id,
            seed_test_data["supervisor"].nombre_completo, "SUPERVISOR",
            CheckFallaDTO(
                operacion_id=uuid4(), evento_esperado_id=esperado, estado=EstadoFalla.INCOMPLETA,
                mecanicos_ids=[b.id, mecanico_c.id], taller_id=taller.id,
            ),
        )

    activos = set((await db_session.scalars(select(TallerAsignacionFalla.mecanico_id).where(
        TallerAsignacionFalla.detalle_id == detalle_id, TallerAsignacionFalla.is_activo.is_(True)
    ))).all())
    eventos = list((await db_session.scalars(select(TallerFallaEvento).where(
        TallerFallaEvento.detalle_id == detalle_id, TallerFallaEvento.tipo_evento == "INCOMPLETA"
    ))).all())
    autores = set((await db_session.scalars(select(TallerFallaEventoMecanico.mecanico_id).where(
        TallerFallaEventoMecanico.evento_id == primera.evento_id
    ))).all())
    ubicaciones = await db_session.scalar(select(func.count(TallerResultadoUbicacion.id)).where(
        TallerResultadoUbicacion.evento_id == primera.evento_id
    ))

    assert primera.evento_id == segunda.evento_id
    assert activos == {b.id, mecanico_c.id}
    assert a.id not in activos  # A queda en el historial, deja de ser asignación actual.
    assert autores == {b.id, mecanico_c.id}
    assert primera.mecanicos_avance and {m.id for m in primera.mecanicos_avance} == autores
    assert ubicaciones == 1
    assert len(eventos) == 1
    ficha = await taller_service.get_solicitud(db_session, solicitud.id)
    detalle = next(item for item in ficha.detalles if item.id == detalle_id)
    assert {m.id for m in detalle.mecanicos_avance} == autores
    assert detalle.ubicacion.taller_responsable.id == taller.id
    assert len(detalle.historial_eventos[-1].historial_ubicaciones) == 1


@pytest.mark.asyncio
async def test_mecanico_no_puede_suplantar_supervision_ni_repetir_resuelta(db_session, seed_test_data):
    solicitud, detalle_id = await _crear_solicitud(
        db_session, seed_test_data["conductor"], seed_test_data["falla1"], "PERMISOS"
    )
    taller, _ = await _crear_talleres(db_session)
    esperado = await db_session.scalar(select(TallerFallaEvento.id).where(
        TallerFallaEvento.detalle_id == detalle_id
    ).order_by(TallerFallaEvento.id.desc()).limit(1))
    result = await resultado_falla_service.registrar(
        db_session, solicitud.id, detalle_id, seed_test_data["supervisor"].id,
        seed_test_data["supervisor"].nombre_completo, "SUPERVISOR",
        CheckFallaDTO(
            operacion_id=uuid4(), evento_esperado_id=esperado, estado=EstadoFalla.RESUELTA,
            mecanicos_ids=[seed_test_data["mecanico1"].id], taller_id=taller.id,
        ),
    )
    evento_count = await db_session.scalar(select(func.count(TallerFallaEvento.id)).where(
        TallerFallaEvento.detalle_id == detalle_id
    ))
    with pytest.raises(PermissionException):
        await resultado_falla_service.registrar(
            db_session, solicitud.id, detalle_id, seed_test_data["mecanico1"].id,
            seed_test_data["mecanico1"].nombre_completo, "MECANICO",
            CheckFallaDTO(
                operacion_id=uuid4(), evento_esperado_id=result.evento_id, estado=EstadoFalla.RESUELTA,
                mecanicos_ids=[], taller_id=taller.id,
            ),
        )
    assert await db_session.scalar(select(func.count(TallerFallaEvento.id)).where(
        TallerFallaEvento.detalle_id == detalle_id
    )) == evento_count
    with pytest.raises(PermissionException):
        await resultado_falla_service.registrar(
            db_session, solicitud.id, detalle_id, seed_test_data["mecanico1"].id,
            seed_test_data["mecanico1"].nombre_completo, "SUPERVISOR",
            CheckFallaDTO(
                operacion_id=uuid4(), evento_esperado_id=result.evento_id, estado=EstadoFalla.INCOMPLETA,
                mecanicos_ids=[], taller_id=taller.id,
            ),
        )


@pytest.mark.asyncio
async def test_resultado_externo_sin_autores_y_correccion_inmutable(db_session, seed_test_data):
    solicitud, detalle_id = await _crear_solicitud(
        db_session, seed_test_data["conductor"], seed_test_data["falla1"], "EXTERNO"
    )
    interno, externo = await _crear_talleres(db_session)
    esperado = await db_session.scalar(select(TallerFallaEvento.id).where(
        TallerFallaEvento.detalle_id == detalle_id
    ).order_by(TallerFallaEvento.id.desc()).limit(1))
    dto = CheckFallaDTO(
        operacion_id=uuid4(), evento_esperado_id=esperado, estado=EstadoFalla.RESUELTA,
        mecanicos_ids=[], taller_id=externo.id,
    )
    result = await resultado_falla_service.registrar(
        db_session, solicitud.id, detalle_id, seed_test_data["supervisor"].id,
        seed_test_data["supervisor"].nombre_completo, "SUPERVISOR", dto,
    )
    assert result.mecanicos_resolvieron == []
    assert result.ubicacion.taller_responsable.tipo == "EXTERNO"

    correction = await resultado_falla_service.corregir_ubicacion(
        db_session, solicitud.id, detalle_id, result.evento_id, seed_test_data["supervisor"].id,
        seed_test_data["supervisor"].nombre_completo, "SUPERVISOR",
        CorregirUbicacionDTO(
            operacion_id=uuid4(), ubicacion_esperada_id=result.ubicacion.id,
            taller_id=interno.id, motivo="Orden de servicio confirma el taller interno",
        ),
    )
    historial = list((await db_session.scalars(select(TallerResultadoUbicacion).where(
        TallerResultadoUbicacion.evento_id == result.evento_id
    ).order_by(TallerResultadoUbicacion.version))).all())
    assert correction.version == 2
    assert [u.version for u in historial] == [1, 2]
    assert await supervision_repository.count_auditoria(
        db_session, ciudad_id=interno.ciudad_id, taller_id=interno.id, ambito="ACTUAL"
    ) == 1
    assert await supervision_repository.count_auditoria(
        db_session, ciudad_id=externo.ciudad_id, taller_id=externo.id, ambito="HISTORICO"
    ) == 1
    ficha = await taller_service.get_solicitud(db_session, solicitud.id)
    detalle = next(item for item in ficha.detalles if item.id == detalle_id)
    evento = next(item for item in detalle.historial_eventos if item.id == result.evento_id)
    assert detalle.ubicacion_vigente_id == correction.id
    assert [item.version for item in evento.historial_ubicaciones] == [1, 2]


@pytest.mark.asyncio
async def test_admin_asignado_puede_ser_autor_y_resolutor(db_session, seed_test_data):
    from app.modules.auth.models.usuario import Usuario
    from app.core.security import get_password_hash

    conductor = seed_test_data["conductor"]
    mecanico = seed_test_data["mecanico1"]
    admin = Usuario(
        nombre="Admin", apellido="Sistema", username="admin-unit@narbus.cl",
        password_hash=get_password_hash("password123"), rol_id=4, is_active=True,
    )
    db_session.add(admin)
    await db_session.flush()

    solicitud, detalle_id = await _crear_solicitud(db_session, conductor, seed_test_data["falla1"], "ADMIN-AUTOR")
    taller, _ = await _crear_talleres(db_session)

    # El admin y el mecánico están asignados conjuntamente a la falla
    db_session.add_all([
        TallerAsignacionFalla(solicitud_id=solicitud.id, detalle_id=detalle_id, mecanico_id=admin.id,
                             asignado_por_id=admin.id, origen="AUTOASIGNACION", is_activo=True),
        TallerAsignacionFalla(solicitud_id=solicitud.id, detalle_id=detalle_id, mecanico_id=mecanico.id,
                             asignado_por_id=admin.id, origen="AUTOASIGNACION", is_activo=True),
    ])
    await db_session.flush()

    esperado = await db_session.scalar(select(TallerFallaEvento.id).where(
        TallerFallaEvento.detalle_id == detalle_id
    ).order_by(TallerFallaEvento.id.desc()).limit(1))

    dto = CheckFallaDTO(
        operacion_id=uuid4(),
        evento_esperado_id=esperado,
        estado=EstadoFalla.RESUELTA,
        taller_id=taller.id,
    )

    # El mecánico marca la falla resuelta (el equipo incluye al admin)
    result = await resultado_falla_service.registrar(
        db_session, solicitud.id, detalle_id, mecanico.id,
        mecanico.nombre_completo, "MECANICO", dto,
    )

    assert result.resuelto is True
    assert result.ubicacion.id is not None
    autores_ids = [m.id for m in result.mecanicos_resolvieron]
    assert admin.id in autores_ids
    assert mecanico.id in autores_ids


@pytest.mark.asyncio
async def test_supervisor_termina_falla_taller_externo_omitiendo_mecanicos_ids(db_session, seed_test_data):
    solicitud, detalle_id = await _crear_solicitud(
        db_session, seed_test_data["conductor"], seed_test_data["falla1"], "EXT-OMIT"
    )
    _, externo = await _crear_talleres(db_session)
    esperado = await db_session.scalar(select(TallerFallaEvento.id).where(
        TallerFallaEvento.detalle_id == detalle_id
    ).order_by(TallerFallaEvento.id.desc()).limit(1))

    # El supervisor envía taller externo sin mecanicos_ids (None)
    dto = CheckFallaDTO(
        operacion_id=uuid4(), evento_esperado_id=esperado, estado=EstadoFalla.RESUELTA,
        taller_id=externo.id,
    )
    result = await resultado_falla_service.registrar(
        db_session, solicitud.id, detalle_id, seed_test_data["supervisor"].id,
        seed_test_data["supervisor"].nombre_completo, "SUPERVISOR", dto,
    )
    assert result.resuelto is True
    assert result.mecanicos_resolvieron == []
    assert result.ubicacion.taller_responsable.tipo == "EXTERNO"


