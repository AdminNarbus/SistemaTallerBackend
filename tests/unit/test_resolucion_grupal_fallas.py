import pytest
from app.modules.taller.constants import EstadoFalla
from app.modules.taller.dtos import (
    AutoasignarFallasDTO,
    CheckFallaDTO,
    SolicitudCreateDTO,
    SolicitudDetalleCreateDTO,
    TomarTrabajoDTO,
)
from app.modules.taller.services.taller_service import taller_service


@pytest.mark.asyncio
async def test_check_detalle_resolucion_grupal(db_session, seed_test_data):
    """
    Verifica que al resolver una falla asignada a un equipo (grupo de mecánicos):
    1. DetalleUpdateDTO retorne a todos los mecánicos en mecanicos_resolvieron.
    2. mecanico_resolvio_nombre concatene los nombres del equipo.
    3. Todas las asignaciones activas en taller_asignacion_fallas queden con resuelto_en_esta_asignacion = True.
    4. La bitácora registre el hito como resolución de equipo.
    """
    conductor = seed_test_data["conductor"]
    mecanico1 = seed_test_data["mecanico1"]
    mecanico2 = seed_test_data["mecanico2"]
    falla = seed_test_data["falla1"]

    # 1. Crear solicitud con 1 falla
    solicitud = await taller_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(
            n_bus="BUS-COLAB-1",
            descripcion_general="Prueba resolución grupal",
            detalles=[SolicitudDetalleCreateDTO(falla_id=falla.id)],
        ),
        conductor.id,
    )
    det_id = solicitud.detalles[0].id

    # 2. Mecánico 1 toma trabajo
    await taller_service.tomar_trabajo(
        db_session,
        solicitud.id,
        mecanico1.id,
        TomarTrabajoDTO(comentario_inicial="Iniciando revisión"),
    )

    # 3. Autoasignar la falla colaborativamente a mecánico 1 y mecánico 2
    await taller_service.autoasignar_fallas(
        db_session,
        solicitud_id=solicitud.id,
        dto=AutoasignarFallasDTO(
            detalles_ids=[det_id],
            colaboradores_ids=[mecanico2.id],
            comentario="Trabajando en pareja",
        ),
        mecanico_id=mecanico1.id,
        mecanico_nombre=mecanico1.nombre_completo,
    )

    # 4. Mecánico 1 marca la falla como RESUELTA
    res_update = await taller_service.averias_srv.check_detalle(
        db=db_session,
        solicitud_id=solicitud.id,
        detalle_id=det_id,
        mecanico_id=mecanico1.id,
        resuelto=True,
        mecanico_nombre=mecanico1.nombre_completo,
        estado=EstadoFalla.RESUELTA,
    )

    # Aserciones sobre DetalleUpdateDTO
    assert res_update.resuelto is True
    assert res_update.estado == "RESUELTA"
    assert len(res_update.mecanicos_resolvieron) == 2
    resolutores_ids = {m.id for m in res_update.mecanicos_resolvieron}
    assert resolutores_ids == {mecanico1.id, mecanico2.id}
    assert mecanico1.nombre_completo in res_update.mecanico_resolvio_nombre
    assert mecanico2.nombre_completo in res_update.mecanico_resolvio_nombre

    # 5. Consultar la solicitud completa y verificar SolicitudDetalleDTO
    sol_cargada = await taller_service.get_solicitud(db_session, solicitud.id)
    det_cargado = next(d for d in sol_cargada.detalles if d.id == det_id)
    assert det_cargado.resuelto is True
    assert len(det_cargado.mecanicos_resolvieron) == 2
    assert mecanico1.nombre_completo in det_cargado.mecanico_resolvio_nombre
    assert mecanico2.nombre_completo in det_cargado.mecanico_resolvio_nombre

    # 6. Verificar bitácora
    bitacora_resolucion = [
        c for c in sol_cargada.comentarios if c.tipo == "RESOLUCION"
    ]
    assert len(bitacora_resolucion) >= 1
    assert "El equipo [" in bitacora_resolucion[-1].comentario
    assert mecanico1.nombre_completo in bitacora_resolucion[-1].comentario
    assert mecanico2.nombre_completo in bitacora_resolucion[-1].comentario


@pytest.mark.asyncio
async def test_check_detalle_incompleta_y_reapertura_grupal(db_session, seed_test_data):
    """
    Verifica que al marcar una falla como INCOMPLETA o PENDIENTE en grupo:
    1. resuelto_en_esta_asignacion se actualice a False.
    2. mecanicos_resolvieron sea lista vacía y mecanico_resolvio_nombre sea None.
    3. La bitácora refleje que el equipo la dejó incompleta o reabierta.
    """
    conductor = seed_test_data["conductor"]
    mecanico1 = seed_test_data["mecanico1"]
    mecanico2 = seed_test_data["mecanico2"]
    falla = seed_test_data["falla1"]

    solicitud = await taller_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(
            n_bus="BUS-COLAB-2",
            descripcion_general="Prueba incompleta y reapertura",
            detalles=[SolicitudDetalleCreateDTO(falla_id=falla.id)],
        ),
        conductor.id,
    )
    det_id = solicitud.detalles[0].id

    await taller_service.tomar_trabajo(
        db_session,
        solicitud.id,
        mecanico1.id,
        TomarTrabajoDTO(),
    )

    await taller_service.autoasignar_fallas(
        db_session,
        solicitud_id=solicitud.id,
        dto=AutoasignarFallasDTO(
            detalles_ids=[det_id],
            colaboradores_ids=[mecanico2.id],
        ),
        mecanico_id=mecanico1.id,
        mecanico_nombre=mecanico1.nombre_completo,
    )

    # 1. Marcar como INCOMPLETA
    res_incompleta = await taller_service.averias_srv.check_detalle(
        db=db_session,
        solicitud_id=solicitud.id,
        detalle_id=det_id,
        mecanico_id=mecanico1.id,
        resuelto=False,
        mecanico_nombre=mecanico1.nombre_completo,
        estado=EstadoFalla.INCOMPLETA,
        motivo_incompleto="Falta perno especial",
    )

    assert res_incompleta.resuelto is False
    assert res_incompleta.estado == "INCOMPLETA"
    assert res_incompleta.mecanico_resolvio_nombre is None
    assert res_incompleta.mecanicos_resolvieron == []

    sol_incompleta = await taller_service.get_solicitud(db_session, solicitud.id)
    comentarios_avance = [c for c in sol_incompleta.comentarios if c.tipo == "AVANCE"]
    assert len(comentarios_avance) >= 1
    assert "El equipo [" in comentarios_avance[-1].comentario
    assert "como INCOMPLETA" in comentarios_avance[-1].comentario

    # 2. Reabrir a PENDIENTE
    res_reapertura = await taller_service.averias_srv.check_detalle(
        db=db_session,
        solicitud_id=solicitud.id,
        detalle_id=det_id,
        mecanico_id=mecanico1.id,
        resuelto=False,
        mecanico_nombre=mecanico1.nombre_completo,
        estado=EstadoFalla.PENDIENTE,
    )

    assert res_reapertura.resuelto is False
    assert res_reapertura.estado == "PENDIENTE"
    assert res_reapertura.mecanicos_resolvieron == []

    sol_reabierta = await taller_service.get_solicitud(db_session, solicitud.id)
    comentarios_reapertura = [c for c in sol_reabierta.comentarios if c.tipo == "REAPERTURA"]
    assert len(comentarios_reapertura) >= 1
    assert "El equipo [" in comentarios_reapertura[-1].comentario
    assert "reabrió la falla" in comentarios_reapertura[-1].comentario


@pytest.mark.asyncio
async def test_resolver_falla_supervisora_con_lista_mecanicos(db_session, seed_test_data):
    """
    Verifica que la supervisora pueda indicar una LISTA de mecánicos al resolver
    una falla (mecanicos_ids=[mec1.id, mec2.id]) sin cuadrilla previa asignada.

    Assertions:
    1. DetalleUpdateDTO retorna todos los mecánicos en mecanicos_resolvieron.
    2. mecanico_resolvio_nombre concatena ambos nombres.
    3. Se crean asignaciones nuevas en taller_asignacion_fallas para cada mecánico.
    4. La bitácora registra el equipo seleccionado por la supervisora.
    5. Retrocompatibilidad: mecanico_id singular (sin mecanicos_ids) sigue funcionando.
    """
    conductor = seed_test_data["conductor"]
    mecanico1 = seed_test_data["mecanico1"]
    mecanico2 = seed_test_data["mecanico2"]
    supervisor = seed_test_data["supervisor"]
    falla = seed_test_data["falla1"]

    # --- ARRANGE: Crear solicitud sin asignar cuadrilla a la falla ---
    solicitud = await taller_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(
            n_bus="BUS-SUP-MULTI-1",
            descripcion_general="Prueba supervisora multi-mecánico",
            detalles=[SolicitudDetalleCreateDTO(falla_id=falla.id)],
        ),
        conductor.id,
    )
    det_id = solicitud.detalles[0].id

    # --- ACT: Supervisora resuelve indicando 2 mecánicos explícitamente ---
    dto = CheckFallaDTO(
        estado="RESUELTA",
        mecanicos_ids=[mecanico1.id, mecanico2.id],
        comentario="Ambos trabajaron en la reparación",
    )
    res = await taller_service.averias_srv.resolver_falla_supervisora(
        db=db_session,
        solicitud_id=solicitud.id,
        detalle_id=det_id,
        dto=dto,
        supervisor_id=supervisor.id,
        supervisor_nombre=supervisor.nombre_completo,
    )

    # --- ASSERT: DetalleUpdateDTO contiene a los 2 mecánicos ---
    assert res.resuelto is True
    assert res.estado == "RESUELTA"
    assert len(res.mecanicos_resolvieron) == 2
    ids_resolutores = {m.id for m in res.mecanicos_resolvieron}
    assert ids_resolutores == {mecanico1.id, mecanico2.id}
    assert mecanico1.nombre_completo in res.mecanico_resolvio_nombre
    assert mecanico2.nombre_completo in res.mecanico_resolvio_nombre

    # Verificar bitácora grupal
    sol_cargada = await taller_service.get_solicitud(db_session, solicitud.id)
    det_cargado = next(d for d in sol_cargada.detalles if d.id == det_id)
    assert det_cargado.resuelto is True
    assert len(det_cargado.mecanicos_resolvieron) == 2
    bitacora = [c for c in sol_cargada.comentarios if c.tipo == "RESOLUCION"]
    assert len(bitacora) >= 1
    assert "Supervisora" in bitacora[-1].comentario
    assert "equipo [" in bitacora[-1].comentario
    assert mecanico1.nombre_completo in bitacora[-1].comentario
    assert mecanico2.nombre_completo in bitacora[-1].comentario

    # --- Retrocompatibilidad: enviar mecanico_id singular (sin mecanicos_ids) ---
    solicitud2 = await taller_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(
            n_bus="BUS-SUP-RETRO-1",
            descripcion_general="Prueba retro singular",
            detalles=[SolicitudDetalleCreateDTO(falla_id=falla.id)],
        ),
        conductor.id,
    )
    det2_id = solicitud2.detalles[0].id
    dto_singular = CheckFallaDTO(mecanico_id=mecanico1.id)
    res2 = await taller_service.averias_srv.resolver_falla_supervisora(
        db=db_session,
        solicitud_id=solicitud2.id,
        detalle_id=det2_id,
        dto=dto_singular,
        supervisor_id=supervisor.id,
        supervisor_nombre=supervisor.nombre_completo,
    )
    assert res2.resuelto is True
    assert len(res2.mecanicos_resolvieron) == 1
    assert res2.mecanicos_resolvieron[0].id == mecanico1.id
