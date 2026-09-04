import pytest
from datetime import datetime, timezone, timedelta
from app.modules.mantencion.repository.mantencion_repository import (
    _calcular_duracion_minutos,
    mantencion_repository,
)
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import (
    SolicitudCreateDTO,
    SolicitudDetalleCreateDTO,
    AutoasignarFallasDTO,
    FinalizarSolicitudDTO,
    TerminarAvanceDTO,
    ReportarRepuestoDTO,
)
from app.core.exceptions import BusinessRuleException


def test_calcular_duracion_minutos_unit():
    """Verifica que _calcular_duracion_minutos maneja correctamente combinaciones de datetimes."""
    # 1. Inputs None
    assert _calcular_duracion_minutos(None, datetime.now()) == 0
    assert _calcular_duracion_minutos(datetime.now(), None) == 0
    assert _calcular_duracion_minutos(None, None) == 0

    # 2. Ambos naive
    t1 = datetime(2026, 9, 3, 10, 0, 0)
    t2 = datetime(2026, 9, 3, 10, 25, 0)
    assert _calcular_duracion_minutos(t1, t2) == 25

    # Menos de 1 minuto retorna mínimo 1
    t_casi = datetime(2026, 9, 3, 10, 0, 30)
    assert _calcular_duracion_minutos(t1, t_casi) == 1

    # Fecha fin menor o igual retorna mínimo 1
    assert _calcular_duracion_minutos(t2, t1) == 1

    # 3. Uno aware (UTC) y uno naive (simulando server_default func.now() y datetime.now())
    utc_t1 = datetime(2026, 9, 3, 14, 0, 0, tzinfo=timezone.utc)
    naive_t2 = datetime(2026, 9, 3, 15, 30, 0)  # Naive
    # No debe lanzar TypeError: can't subtract offset-naive and offset-aware datetimes
    res = _calcular_duracion_minutos(utc_t1, naive_t2)
    assert res >= 1

    # 4. Ambos aware
    utc_t2 = datetime(2026, 9, 3, 15, 0, 0, tzinfo=timezone.utc)
    assert _calcular_duracion_minutos(utc_t1, utc_t2) == 60


@pytest.mark.asyncio
async def test_autoasignacion_colaborativa_con_colaboradores_ids(db_session, seed_test_data):
    """Verifica que autoasignar_fallas_mecanico asigne atómicamente al mecánico principal y a colaboradores."""
    conductor_id = seed_test_data["conductor"].id
    mecanico1_id = seed_test_data["mecanico1"].id
    mecanico2_id = seed_test_data["mecanico2"].id
    falla1_id = seed_test_data["falla1"].id
    falla2_id = seed_test_data["falla2"].id

    # 1. Crear solicitud con 2 fallas
    dto_crear = SolicitudCreateDTO(
        n_bus="BUS-COLAB",
        descripcion_general="Prueba de asignación colaborativa",
        detalles=[
            SolicitudDetalleCreateDTO(falla_id=falla1_id, descripcion_personalizada="Falla 1"),
            SolicitudDetalleCreateDTO(falla_id=falla2_id, descripcion_personalizada="Falla 2"),
        ],
    )
    solicitud = await mantencion_service.create_solicitud(db_session, dto_crear, conductor_id)
    det1_id = solicitud.detalles[0].id
    det2_id = solicitud.detalles[1].id

    # 2. Mecánico 1 se autoasigna Falla 1 y Falla 2 con Mecánico 2 como colaborador
    dto_auto = AutoasignarFallasDTO(
        detalles_ids=[det1_id, det2_id],
        comentario="Trabajando en equipo en fallas 1 y 2",
        colaboradores_ids=[mecanico2_id],
    )
    sol_auto = await mantencion_service.autoasignar_fallas(
        db_session, solicitud_id=solicitud.id, dto=dto_auto, mecanico_id=mecanico1_id
    )

    assert sol_auto.estado == "EN_REPARACION"

    # Verificar que ambos mecánicos tienen presencia activa en la solicitud
    mecanicos_activos_ids = {m.mecanico_id for m in sol_auto.mecanicos if m.is_activo}
    assert mecanico1_id in mecanicos_activos_ids
    assert mecanico2_id in mecanicos_activos_ids

    # Verificar que ambas fallas tienen asignados a ambos mecánicos
    for det in sol_auto.detalles:
        mecs_en_falla = {m.id for m in det.mecanicos_asignados}
        assert mecanico1_id in mecs_en_falla
        assert mecanico2_id in mecs_en_falla


@pytest.mark.asyncio
async def test_finalizar_solicitud_con_fechas_timezone_aware(db_session, seed_test_data):
    """Verifica que finalizar_solicitud no falle con error 500 cuando hay fechas aware en la base de datos."""
    conductor_id = seed_test_data["conductor"].id
    mecanico1_id = seed_test_data["mecanico1"].id
    falla1_id = seed_test_data["falla1"].id

    dto_crear = SolicitudCreateDTO(
        n_bus="BUS-BUG500",
        descripcion_general="Prueba duracion_minutos naive vs aware",
        detalles=[
            SolicitudDetalleCreateDTO(falla_id=falla1_id, descripcion_personalizada="Falla para cierre"),
        ],
    )
    solicitud = await mantencion_service.create_solicitud(db_session, dto_crear, conductor_id)
    det_id = solicitud.detalles[0].id

    # Autoasignar falla
    dto_auto = AutoasignarFallasDTO(detalles_ids=[det_id])
    sol_auto = await mantencion_service.autoasignar_fallas(
        db_session, solicitud_id=solicitud.id, dto=dto_auto, mecanico_id=mecanico1_id
    )

    # Simular fecha_asignacion aware en base de datos
    for mec in sol_auto.mecanicos:
        mec.fecha_asignacion = datetime.now(timezone.utc) - timedelta(minutes=45)

    # Marcar falla resuelta
    await mantencion_service.check_detalle(
        db_session, solicitud_id=solicitud.id, detalle_id=det_id, mecanico_id=mecanico1_id, resuelto=True
    )

    # Finalizar solicitud (anteriormente causaba TypeError 500 por mezclar naive y aware)
    dto_fin = FinalizarSolicitudDTO(
        comentario_cierre="Trabajo completado exitosamente sin error 500",
        motivo_incompleto_checklist="Pauta no requerida para test",
        liberar_bus_taller=False,
    )
    sol_fin = await mantencion_service.finalizar_solicitud(
        db_session, solicitud_id=solicitud.id, mecanico_cierre_id=mecanico1_id, dto=dto_fin
    )

    assert sol_fin.estado == "FINALIZADO"
    # Verificar que duracion_minutos fue calculada correctamente
    for mec in sol_fin.mecanicos:
        assert mec.duracion_minutos is not None
        assert mec.duracion_minutos >= 1


@pytest.mark.asyncio
async def test_create_solicitud_con_categoria_id_directa(db_session, seed_test_data):
    """Verifica que el chofer pueda reportar directamente seleccionando categoria_id."""
    conductor_id = seed_test_data["conductor"].id
    cat_frenos_id = seed_test_data["falla2"].categoria_id  # 2 = Frenos

    dto_crear = SolicitudCreateDTO(
        n_bus="BUS-CAT-DIRECTA",
        descripcion_general="Reporte directo por categoría sin subcategorías",
        detalles=[
            SolicitudDetalleCreateDTO(
                categoria_id=cat_frenos_id,
                descripcion_personalizada="Pedal esponjoso y ruidos",
            ),
        ],
    )
    solicitud = await mantencion_service.create_solicitud(db_session, dto_crear, conductor_id)

    assert solicitud.id is not None
    assert len(solicitud.detalles) == 1
    det = solicitud.detalles[0]
    assert det.falla_id is not None
    assert det.categoria_id == cat_frenos_id
    assert det.categoria_nombre == "Frenos"
    assert det.descripcion_personalizada == "Pedal esponjoso y ruidos"


@pytest.mark.asyncio
async def test_terminar_avance_grupal_cronometrado(db_session, seed_test_data):
    """
    Verifica que terminar_avance cierre la sesión para todos los integrantes del grupo,
    calculando inicio, fin y duracion_minutos para cada mecánico involucrado.
    """
    from app.modules.mantencion.dtos.mantencion_dto import TerminarAvanceDTO

    conductor_id = seed_test_data["conductor"].id
    mecanico1_id = seed_test_data["mecanico1"].id
    mecanico2_id = seed_test_data["mecanico2"].id
    falla1_id = seed_test_data["falla1"].id

    # 1. Crear solicitud
    dto_crear = SolicitudCreateDTO(
        n_bus="BUS-TIMEADO",
        descripcion_general="Prueba de terminar avance timeado grupal",
        detalles=[
            SolicitudDetalleCreateDTO(falla_id=falla1_id, descripcion_personalizada="Avería compartida"),
        ],
    )
    solicitud = await mantencion_service.create_solicitud(db_session, dto_crear, conductor_id)
    det_id = solicitud.detalles[0].id

    # 2. Mecánico 1 toma la falla con Mecánico 2 como colaborador
    dto_auto = AutoasignarFallasDTO(
        detalles_ids=[det_id],
        comentario="Inicio de reparación en pareja",
        colaboradores_ids=[mecanico2_id],
    )
    sol_auto = await mantencion_service.autoasignar_fallas(
        db_session, solicitud_id=solicitud.id, dto=dto_auto, mecanico_id=mecanico1_id
    )
    assert sol_auto.estado == "EN_REPARACION"

    # Simular que comenzaron hace 30 minutos
    hace_30 = datetime.now() - timedelta(minutes=30)
    for mec in sol_auto.mecanicos:
        mec.fecha_asignacion = hace_30

    # 3. Mecánico 1 ejecuta 'Terminar Avance' para todo el grupo
    dto_terminar = TerminarAvanceDTO(
        comentario="Pausa de almuerzo del equipo; avanzamos un 50%",
    )
    sol_fin_avance = await mantencion_service.terminar_avance(
        db_session,
        solicitud_id=solicitud.id,
        dto=dto_terminar,
        mecanico_id=mecanico1_id,
    )

    # 4. Validar que la solicitud pasó a PENDIENTE
    assert sol_fin_avance.estado == "PENDIENTE"

    # 5. Validar que AMBOS mecánicos quedaron inactivos y con duracion_minutos >= 1
    assert len(sol_fin_avance.mecanicos) == 2
    for mec in sol_fin_avance.mecanicos:
        assert mec.is_activo is False
        assert mec.fecha_desasignacion is not None
        assert mec.duracion_minutos is not None
        assert mec.duracion_minutos >= 1

    # 6. Validar que la bitácora registra el avance grupal
    ultimo_comentario = sol_fin_avance.comentarios[-1]
    assert ultimo_comentario.tipo == "ENTREGA_TURNO"
    assert "avance grupal" in ultimo_comentario.comentario
    assert "Pausa de almuerzo" in ultimo_comentario.comentario

    # 7. Validar que NO aparece en mis_trabajos y SÍ aparece en pendientes
    mis_trabajos_m1 = await mantencion_service.list_mis_trabajos(db_session, mecanico1_id)
    assert not any(s.id == solicitud.id for s in mis_trabajos_m1)

    mis_trabajos_m2 = await mantencion_service.list_mis_trabajos(db_session, mecanico2_id)
    assert not any(s.id == solicitud.id for s in mis_trabajos_m2)

    pendientes = await mantencion_service.list_pendientes(db_session)
    assert any(s.id == solicitud.id for s in pendientes)


@pytest.mark.asyncio
async def test_bloqueo_resolver_falla_con_falta_repuesto(db_session):
    """
    Regla de Negocio:
    1. Una falla en espera de repuesto (falta_repuesto=True) NO puede marcarse como resuelta.
    2. Una falla ya resuelta (resuelto=True) NO puede marcarse con falta de repuesto sin desmarcarla antes.
    3. Al declarar el repuesto como disponible (falta_repuesto=False), se permite marcarla como resuelta.
    """
    mecanico_id = 2
    conductor_id = 3

    # 1. Crear solicitud con 1 falla
    dto_crear = SolicitudCreateDTO(
        n_bus="700",
        descripcion_general="Falla en suspensión neumática",
        detalles=[
            SolicitudDetalleCreateDTO(descripcion_personalizada="Pulmón de aire pinchado"),
        ],
    )
    solicitud = await mantencion_service.create_solicitud(
        db_session, dto=dto_crear, creador_id=conductor_id
    )
    detalle_id = solicitud.detalles[0].id

    # 2. Reportar falta de repuesto para este detalle
    await mantencion_service.reportar_repuesto(
        db_session,
        solicitud_id=solicitud.id,
        detalle_id=detalle_id,
        mecanico_id=mecanico_id,
        dto=ReportarRepuestoDTO(
            falta_repuesto=True,
            comentario="Esperando repuesto de fuelle suspensión",
        ),
    )

    # 3. Intentar marcar la falla como resuelta -> Debe fallar con BusinessRuleException
    with pytest.raises(BusinessRuleException) as exc_info:
        await mantencion_service.check_detalle(
            db_session,
            solicitud_id=solicitud.id,
            detalle_id=detalle_id,
            mecanico_id=mecanico_id,
            resuelto=True,
        )
    assert "espera de repuesto" in str(exc_info.value).lower()

    # 4. Reportar que el repuesto llegó (falta_repuesto=False)
    await mantencion_service.reportar_repuesto(
        db_session,
        solicitud_id=solicitud.id,
        detalle_id=detalle_id,
        mecanico_id=mecanico_id,
        dto=ReportarRepuestoDTO(
            falta_repuesto=False,
            comentario="Llegó el repuesto a bodega",
        ),
    )

    # 5. Ahora sí debe permitir marcarla como resuelta
    sol_ok = await mantencion_service.check_detalle(
        db_session,
        solicitud_id=solicitud.id,
        detalle_id=detalle_id,
        mecanico_id=mecanico_id,
        resuelto=True,
    )
    det_actual = next(d for d in sol_ok.detalles if d.id == detalle_id)
    assert det_actual.resuelto is True
    assert det_actual.falta_repuesto is False

    # 6. Intentar reportar falta de repuesto en una falla que ya está resuelta -> Debe fallar con BusinessRuleException
    with pytest.raises(BusinessRuleException) as exc_rep:
        await mantencion_service.reportar_repuesto(
            db_session,
            solicitud_id=solicitud.id,
            detalle_id=detalle_id,
            mecanico_id=mecanico_id,
            dto=ReportarRepuestoDTO(
                falta_repuesto=True,
                comentario="Intento contradictorio",
            ),
        )
    assert "ya fue marcada como resuelta" in str(exc_rep.value).lower()



