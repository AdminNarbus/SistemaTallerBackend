from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.mantencion.constants import (
    EstadoSolicitud,
    OrigenAsignacion,
    TipoComentarioBitacora,
    TOTAL_ITEMS_PAUTA_PREVENTIVA,
)
from app.modules.mantencion.dtos.mantencion_dto import (
    AgregarColaboradorDTO,
    AutoasignarFallasDTO,
    ComentarioCreateDTO,
    FinalizarSolicitudDTO,
    LiberarTurnoDTO,
    SolicitudCreateDTO,
    SolicitudDetalleCreateDTO,
    TerminarAvanceDTO,
    TomarTrabajoDTO,
)
from app.modules.mantencion.services.mantencion_service import (
    MantencionService,
    mantencion_service,
)
from app.modules.mantencion.utils import (
    calcular_duracion_minutos,
    calcular_horas_en_taller,
    formatear_comentario_cierre,
    recopilar_archivos_fotos,
    validar_fallas_cierre_parcial,
    validar_pauta_preventiva_cierre,
)


# =====================================================================
# 1. Pruebas Unitarias Puras: Funciones de Dominio y Utilidades (AAA)
# =====================================================================


def test_calcular_duracion_minutos_none_o_fechas_vacias():
    """Valida que si alguna de las fechas es None, retorne 0."""
    assert calcular_duracion_minutos(None, None) == 0
    assert calcular_duracion_minutos(datetime.now(), None) == 0
    assert calcular_duracion_minutos(None, datetime.now()) == 0


def test_calcular_duracion_minutos_mismo_tiempo():
    """Valida que si inicio y fin son idénticos pero presentes, retorne mínimo 1 minuto por regla de taller."""
    ahora = datetime.now()
    assert calcular_duracion_minutos(ahora, ahora) == 1


def test_calcular_duracion_minutos_tiempo_positivo_minimo_un_minuto():
    """Cualquier lapso positivo inferior a 60 segundos debe computar al menos 1 minuto."""
    inicio = datetime(2026, 9, 14, 10, 0, 0)
    fin = datetime(2026, 9, 14, 10, 0, 15)
    assert calcular_duracion_minutos(inicio, fin) == 1


def test_calcular_duracion_minutos_calculo_correcto():
    """Calcula correctamente la duración en minutos para varias horas."""
    inicio = datetime(2026, 9, 14, 8, 0, 0)
    fin = datetime(2026, 9, 14, 10, 30, 0)
    assert calcular_duracion_minutos(inicio, fin) == 150


def test_calcular_duracion_minutos_aware_vs_naive():
    """Normaliza correctamente la diferencia entre datetimes aware y naive."""
    inicio = datetime(2026, 9, 14, 8, 0, 0, tzinfo=timezone.utc)
    fin = datetime(2026, 9, 14, 9, 15, 0)  # naive
    duracion = calcular_duracion_minutos(inicio, fin)
    assert duracion == 75


def test_calcular_horas_en_taller_aware_vs_naive():
    """Calcula horas en taller normalizando correctamente entre datetimes aware y naive."""
    inicio = datetime(2026, 9, 14, 8, 0, 0, tzinfo=timezone.utc)
    fin = datetime(2026, 9, 14, 10, 30, 0)  # naive (sin tzinfo)
    horas = calcular_horas_en_taller(inicio, fin)
    assert horas == 2.5


def test_calcular_horas_en_taller_none_o_fechas_vacias():
    """Retorna None si la fecha de inicio es None, o calcula contra ahora si fin es None."""
    assert calcular_horas_en_taller(None, None) is None
    inicio = datetime.now() - timedelta(hours=3)
    horas = calcular_horas_en_taller(inicio, None)
    assert horas is not None
    assert horas >= 3.0


def test_validar_pauta_preventiva_incompleta_sin_motivo_falla():
    """Si la pauta está incompleta y no hay justificación, debe lanzar BusinessRuleException."""
    with pytest.raises(BusinessRuleException) as exc:
        validar_pauta_preventiva_cierre(
            total_items=TOTAL_ITEMS_PAUTA_PREVENTIVA,
            items_respondidos=5,
            motivo_incompleto=None,
        )
    assert "La pauta preventiva está incompleta" in str(exc.value)


def test_validar_pauta_preventiva_incompleta_con_motivo_pasa():
    """Si la pauta está incompleta pero se justifica, retorna el motivo limpio."""
    resultado = validar_pauta_preventiva_cierre(
        total_items=TOTAL_ITEMS_PAUTA_PREVENTIVA,
        items_respondidos=5,
        motivo_incompleto="  Falta rampa para revisión de chasis  ",
    )
    assert resultado == "Falta rampa para revisión de chasis"


def test_validar_pauta_preventiva_completa_pasa():
    """Si todos los ítems fueron respondidos, no requiere justificación."""
    resultado = validar_pauta_preventiva_cierre(
        total_items=TOTAL_ITEMS_PAUTA_PREVENTIVA,
        items_respondidos=TOTAL_ITEMS_PAUTA_PREVENTIVA,
        motivo_incompleto=None,
    )
    assert resultado is None


def test_validar_fallas_cierre_parcial_sin_motivo_falla():
    """Si quedan fallas abiertas y no hay justificación de cierre parcial, debe fallar."""
    with pytest.raises(BusinessRuleException) as exc:
        validar_fallas_cierre_parcial(
            cantidad_fallas_no_resueltas=2,
            motivo_cierre_parcial=None,
        )
    assert "Para liberar el bus con cierre parcial" in str(exc.value)


def test_validar_fallas_cierre_parcial_con_motivo_pasa():
    """Si quedan fallas abiertas pero se justifica el cierre parcial, retorna el texto limpio."""
    resultado = validar_fallas_cierre_parcial(
        cantidad_fallas_no_resueltas=1,
        motivo_cierre_parcial="  Repuesto de sensor ABS en tránsito desde Santiago  ",
    )
    assert resultado == "Repuesto de sensor ABS en tránsito desde Santiago"


def test_validar_fallas_cierre_parcial_sin_fallas_pasa():
    """Si no quedan fallas abiertas, no requiere motivo."""
    resultado = validar_fallas_cierre_parcial(
        cantidad_fallas_no_resueltas=0,
        motivo_cierre_parcial=None,
    )
    assert resultado is None


def test_formatear_comentario_cierre_liberar_bus():
    """Verifica el formato del texto para cierre con liberación de bus."""
    texto = formatear_comentario_cierre(
        mecanico_nombre="Juan Pérez",
        liberar_bus=True,
        comentario_cierre="Trabajos concluidos con éxito",
    )
    assert "Juan Pérez finalizó los trabajos de la OT y liberó el bus para operaciones." in texto
    assert "Comentario de cierre: Trabajos concluidos con éxito." in texto


def test_formatear_comentario_cierre_sin_liberar_bus():
    """Verifica el formato del texto para cierre sin liberación de bus."""
    texto = formatear_comentario_cierre(
        mecanico_nombre="Carlos Soto",
        liberar_bus=False,
        motivo_cierre_parcial="Falta repuesto",
        motivo_incompleto_checklist="Pauta en 80%",
    )
    assert "Carlos Soto finalizó los trabajos de la OT (el bus permanece en taller)." in texto
    assert "Motivo cierre parcial: Falta repuesto." in texto
    assert "Justificación pauta preventiva: Pauta en 80%." in texto


def test_recopilar_archivos_fotos_deduplicacion():
    """Verifica que recopilar_archivos_fotos descarte duplicados y valores None."""
    f1 = MagicMock(filename="foto1.jpg")
    f2 = MagicMock(filename="foto2.png")
    
    # Simular lista con duplicados
    archivos = recopilar_archivos_fotos(foto=f1, fotos=[f1, f2, None])
    assert len(archivos) == 2
    assert archivos[0].filename == "foto1.jpg"
    assert archivos[1].filename == "foto2.png"


# =====================================================================
# 2. Pruebas Unitarias Aisladas con Mocks: MantencionService (AAA)
# =====================================================================


@pytest.mark.asyncio
async def test_get_solicitud_no_existente_lanza_not_found():
    """MantencionService.get_solicitud lanza NotFoundException si el repositorio retorna None."""
    # Arrange
    mock_repo = AsyncMock()
    mock_repo.get_solicitud_dto_by_id.return_value = None
    service = MantencionService(repository=mock_repo)
    mock_db = AsyncMock()

    # Act & Assert
    with pytest.raises(NotFoundException) as exc:
        await service.get_solicitud(mock_db, solicitud_id=999)
    assert "no encontrada" in str(exc.value)
    mock_repo.get_solicitud_dto_by_id.assert_awaited_once_with(mock_db, 999)


@pytest.mark.asyncio
async def test_autoasignar_fallas_vacias_lanza_business_rule():
    """autoasignar_fallas lanza BusinessRuleException si la lista de fallas está vacía."""
    # Arrange
    mock_repo = AsyncMock()
    mock_solicitud = MagicMock(detalles=[])
    mock_repo.get_solicitud_operacional.return_value = mock_solicitud
    service = MantencionService(repository=mock_repo)
    mock_db = AsyncMock()

    dto = AutoasignarFallasDTO(detalles_ids=[])

    # Act & Assert
    with pytest.raises(BusinessRuleException) as exc:
        await service.autoasignar_fallas(mock_db, solicitud_id=1, dto=dto, mecanico_id=10)
    assert "al menos una falla" in str(exc.value)


@pytest.mark.asyncio
async def test_autoasignar_fallas_id_no_pertenece_lanza_not_found():
    """autoasignar_fallas lanza NotFoundException si el ID de falla no pertenece a la solicitud."""
    # Arrange
    mock_repo = AsyncMock()
    mock_det = MagicMock(id=5)
    mock_solicitud = MagicMock(detalles=[mock_det])
    mock_repo.get_solicitud_operacional.return_value = mock_solicitud
    service = MantencionService(repository=mock_repo)
    mock_db = AsyncMock()

    dto = AutoasignarFallasDTO(detalles_ids=[99])

    # Act & Assert
    with pytest.raises(NotFoundException) as exc:
        await service.autoasignar_fallas(mock_db, solicitud_id=1, dto=dto, mecanico_id=10)
    assert "no pertenece a esta solicitud" in str(exc.value)


@pytest.mark.asyncio
async def test_agregar_colaborador_estado_invalido_lanza_business_rule():
    """agregar_colaborador rechaza solicitudes que no estén EN_REPARACION."""
    # Arrange
    mock_repo = AsyncMock()
    mock_solicitud = MagicMock(estado=EstadoSolicitud.REPORTADO.value)
    mock_repo.get_solicitud_operacional.return_value = mock_solicitud
    service = MantencionService(repository=mock_repo)
    mock_db = AsyncMock()

    dto = AgregarColaboradorDTO(colaborador_id=20)

    # Act & Assert
    with pytest.raises(BusinessRuleException) as exc:
        await service.agregar_colaborador(mock_db, solicitud_id=1, mecanico_id=10, dto=dto)
    assert "EN_REPARACION" in str(exc.value)


@pytest.mark.asyncio
async def test_agregar_colaborador_a_si_mismo_lanza_business_rule():
    """agregar_colaborador prohíbe que un mecánico se agregue a sí mismo."""
    # Arrange
    mock_repo = AsyncMock()
    mock_m = MagicMock(mecanico_id=10, is_activo=True)
    mock_solicitud = MagicMock(
        estado=EstadoSolicitud.EN_REPARACION.value,
        mecanicos=[mock_m],
    )
    mock_repo.get_solicitud_operacional.return_value = mock_solicitud
    service = MantencionService(repository=mock_repo)
    mock_db = AsyncMock()

    dto = AgregarColaboradorDTO(colaborador_id=10)

    # Act & Assert
    with pytest.raises(BusinessRuleException) as exc:
        await service.agregar_colaborador(mock_db, solicitud_id=1, mecanico_id=10, dto=dto)
    assert "a sí mismo" in str(exc.value)


@pytest.mark.asyncio
async def test_desasignar_mecanico_no_activo_lanza_business_rule():
    """desasignar_mecanico lanza BusinessRuleException si el mecánico no está activo."""
    # Arrange
    mock_repo = AsyncMock()
    mock_solicitud = MagicMock(id=1)
    mock_repo.get_solicitud_operacional.return_value = mock_solicitud
    mock_repo.desactivar_mecanicos_por_ids.return_value = []  # ningún registro desactivado
    service = MantencionService(repository=mock_repo)
    mock_db = AsyncMock()

    # Act & Assert
    with pytest.raises(BusinessRuleException) as exc:
        await service.desasignar_mecanico(mock_db, solicitud_id=1, mecanico_id=10)
    assert "no está asignado activamente" in str(exc.value)


@pytest.mark.asyncio
async def test_finalizar_solicitud_no_existente_lanza_not_found():
    """finalizar_solicitud lanza NotFoundException si la orden no existe en base de datos."""
    # Arrange
    mock_repo = AsyncMock()
    mock_repo.get_solicitud_con_detalles.return_value = None
    mock_repo.get_solicitud_operacional.return_value = None
    service = MantencionService(repository=mock_repo)
    mock_db = AsyncMock()

    # Act & Assert
    with pytest.raises(NotFoundException) as exc:
        await service.finalizar_solicitud(
            mock_db,
            solicitud_id=404,
            mecanico_cierre_id=10,
            dto=FinalizarSolicitudDTO(),
        )
    assert "no encontrada" in str(exc.value)


# =====================================================================
# 3. Pruebas de Integración Existentes (con Base de Datos de Prueba)
# =====================================================================


@pytest.mark.asyncio
async def test_create_and_get_solicitud(db_session, seed_test_data):
    """Prueba la creación de una orden de taller y su posterior consulta."""
    creador_id = seed_test_data["conductor"].id
    falla_id = seed_test_data["falla1"].id

    dto = SolicitudCreateDTO(
        n_bus="BUS-101",
        descripcion_general="Ruido extraño en motor",
        detalles=[SolicitudDetalleCreateDTO(falla_id=falla_id, descripcion_personalizada="Humo blanco")],
    )

    solicitud = await mantencion_service.create_solicitud(db_session, dto, creador_id)
    assert solicitud.id is not None
    assert solicitud.n_bus == "BUS-101"
    assert solicitud.estado == "PENDIENTE"
    assert len(solicitud.detalles) == 1
    assert solicitud.detalles[0].falla_id == falla_id

    # Consultar por ID
    fetched = await mantencion_service.get_solicitud(db_session, solicitud.id)
    assert fetched is not None
    assert fetched.id == solicitud.id


@pytest.mark.asyncio
async def test_workflow_tomar_liberar_y_finalizar_trabajo(db_session, seed_test_data):
    """Prueba el ciclo de asignación de mecánico líder/colaborador, entrega de turno y cierre."""
    mecanico1_id = seed_test_data["mecanico1"].id
    mecanico2_id = seed_test_data["mecanico2"].id
    conductor_id = seed_test_data["conductor"].id
    falla_id = seed_test_data["falla2"].id

    # 1. Crear solicitud
    solicitud = await mantencion_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(n_bus="BUS-202", descripcion_general="Frenos desgastados", detalles=[SolicitudDetalleCreateDTO(falla_id=falla_id)]),
        conductor_id,
    )

    # 2. Tomar trabajo con mecánico 1 como líder y mecánico 2 como colaborador
    tomar_dto = TomarTrabajoDTO(colaboradores_ids=[mecanico2_id], comentario_inicial="Iniciando inspección de pastillas")
    sol_en_proceso = await mantencion_service.tomar_trabajo(db_session, solicitud.id, mecanico1_id, tomar_dto)
    assert sol_en_proceso.estado == "EN_REPARACION"
    assert len(sol_en_proceso.mecanicos) == 2

    # 3. Check detalle de falla resuelta por mecánico 1
    detalle_id = sol_en_proceso.detalles[0].id
    dto_checked = await mantencion_service.check_detalle(db_session, solicitud.id, detalle_id, mecanico1_id, True)
    assert dto_checked.resuelto is True
    assert dto_checked.detalle_id == detalle_id

    # 4. Liberar turno (pasa a PENDIENTE, eliminando el estado redundante PENDIENTE_REASIGNACION)
    sol_liberada = await mantencion_service.liberar_turno(
        db_session, solicitud.id, mecanico1_id, LiberarTurnoDTO(comentario="Turno terminado, resta prueba en ruta")
    )
    assert sol_liberada.estado == "PENDIENTE"

    # 5. Mecánico 2 toma el trabajo liberado y lo finaliza
    sol_re_tomada = await mantencion_service.tomar_trabajo(
        db_session, solicitud.id, mecanico2_id, TomarTrabajoDTO(comentario_inicial="Prueba en ruta OK")
    )
    assert sol_re_tomada.estado == "EN_REPARACION"

    sol_final = await mantencion_service.finalizar_solicitud(
        db_session, solicitud.id, mecanico2_id, FinalizarSolicitudDTO(comentario_cierre="Bus 100% operativo")
    )
    assert sol_final.estado == "FINALIZADO"
    assert sol_final.mecanico_cierre_id == mecanico2_id


@pytest.mark.asyncio
async def test_liberar_solicitud_con_fallas_pendientes_pasa_a_liberado(db_session, seed_test_data):
    """Verifica que una orden con fallas sin resolver pase a LIBERADO con motivo_cierre_parcial y libere el bus."""
    from app.modules.mantencion.dtos.mantencion_dto import LiberarSolicitudDTO

    conductor_id = seed_test_data["conductor"].id
    mecanico1_id = seed_test_data["mecanico1"].id
    falla_id = seed_test_data["falla1"].id

    solicitud = await mantencion_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(
            n_bus="BUS-LIB-1",
            descripcion_general="Falla de compresor",
            detalles=[SolicitudDetalleCreateDTO(falla_id=falla_id)],
        ),
        conductor_id,
    )

    # Tomar trabajo
    await mantencion_service.tomar_trabajo(
        db_session, solicitud.id, mecanico1_id, TomarTrabajoDTO(comentario_inicial="Revisando compresor")
    )

    # Liberar solicitud con cierre parcial (falla abierta)
    dto_liberar = LiberarSolicitudDTO(
        motivo_cierre_parcial="Falta repuesto de diafragma, bus liberado para turno local",
        liberar_bus_taller=True,
    )
    sol_liberada = await mantencion_service.liberar_solicitud(
        db_session, solicitud.id, dto_liberar, mecanico1_id, "Mecánico 1"
    )

    assert sol_liberada.estado == "LIBERADO"
    assert sol_liberada.fecha_cierre is None
    assert sol_liberada.motivo_cierre_parcial == "Falta repuesto de diafragma, bus liberado para turno local"

    # Reingreso de bus liberado al taller: tomar trabajo lo devuelve a EN_REPARACION
    sol_retomada = await mantencion_service.tomar_trabajo(
        db_session, solicitud.id, mecanico1_id, TomarTrabajoDTO(comentario_inicial="Llegó repuesto, reparando")
    )
    assert sol_retomada.estado == "EN_REPARACION"



@pytest.mark.asyncio
async def test_desasignacion_mecanico_individual_exception(db_session, seed_test_data):
    """Prueba que intentar desasignar a un mecánico no activo lance BusinessRuleException."""
    conductor_id = seed_test_data["conductor"].id
    mecanico1_id = seed_test_data["mecanico1"].id

    solicitud = await mantencion_service.create_solicitud(
        db_session, SolicitudCreateDTO(n_bus="BUS-303", descripcion_general="Chequeo preventivo"), conductor_id
    )

    with pytest.raises(BusinessRuleException) as exc_info:
        await mantencion_service.desasignar_mecanico(db_session, solicitud.id, mecanico1_id)
    assert "no está asignado activamente" in str(exc_info.value)


@pytest.mark.asyncio
async def test_autoasignar_falla_ocupada_bloquea_con_business_rule(db_session, seed_test_data):
    """Verifica que un mecánico no pueda autoasignarse una falla que ya está tomada por otro mecánico activo."""
    conductor_id = seed_test_data["conductor"].id
    mecanico1_id = seed_test_data["mecanico1"].id
    mecanico2_id = seed_test_data["mecanico2"].id
    falla1 = seed_test_data["falla1"]
    falla2 = seed_test_data["falla2"]

    sol = await mantencion_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(
            n_bus="BUS-999",
            descripcion_general="Doble falla",
            detalles=[
                SolicitudDetalleCreateDTO(falla_id=falla1.id, descripcion_personalizada="Falla 1"),
                SolicitudDetalleCreateDTO(falla_id=falla2.id, descripcion_personalizada="Falla 2"),
            ],
        ),
        conductor_id,
    )
    falla_1_id = sol.detalles[0].id
    falla_2_id = sol.detalles[1].id

    # Mecánico 1 toma Falla 1
    await mantencion_service.autoasignar_fallas(
        db_session,
        solicitud_id=sol.id,
        dto=AutoasignarFallasDTO(detalles_ids=[falla_1_id]),
        mecanico_id=mecanico1_id,
        mecanico_nombre="Mecánico 1",
    )

    # Mecánico 2 intenta tomar la misma Falla 1 -> Debe ser BLOQUEADO con BusinessRuleException
    with pytest.raises(BusinessRuleException) as exc_info:
        await mantencion_service.autoasignar_fallas(
            db_session,
            solicitud_id=sol.id,
            dto=AutoasignarFallasDTO(detalles_ids=[falla_1_id]),
            mecanico_id=mecanico2_id,
            mecanico_nombre="Mecánico 2",
        )
    assert "ya se encuentra tomada activamente" in str(exc_info.value)

    # Mecánico 2 toma la Falla 2 (libre) -> Debe ser EXITOSO
    sol_actualizada = await mantencion_service.autoasignar_fallas(
        db_session,
        solicitud_id=sol.id,
        dto=AutoasignarFallasDTO(detalles_ids=[falla_2_id]),
        mecanico_id=mecanico2_id,
        mecanico_nombre="Mecánico 2",
    )
    assert sol_actualizada.estado == "EN_REPARACION"


@pytest.mark.asyncio
async def test_terminar_avance_aislado_por_mecanico(db_session, seed_test_data):
    """Verifica que terminar_avance solo libere el trabajo del mecánico emisor y mantenga activo a sus compañeros."""
    conductor_id = seed_test_data["conductor"].id
    mecanico1_id = seed_test_data["mecanico1"].id
    mecanico2_id = seed_test_data["mecanico2"].id
    falla1 = seed_test_data["falla1"]
    falla2 = seed_test_data["falla2"]

    sol = await mantencion_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(
            n_bus="BUS-888",
            descripcion_general="Trabajo colaborativo",
            detalles=[
                SolicitudDetalleCreateDTO(falla_id=falla1.id, descripcion_personalizada="Falla A"),
                SolicitudDetalleCreateDTO(falla_id=falla2.id, descripcion_personalizada="Falla B"),
            ],
        ),
        conductor_id,
    )
    falla_a_id = sol.detalles[0].id
    falla_b_id = sol.detalles[1].id

    # Mecánico 1 toma Falla A
    await mantencion_service.autoasignar_fallas(
        db_session, sol.id, AutoasignarFallasDTO(detalles_ids=[falla_a_id]), mecanico1_id, "Mecánico 1"
    )
    # Mecánico 2 toma Falla B
    await mantencion_service.autoasignar_fallas(
        db_session, sol.id, AutoasignarFallasDTO(detalles_ids=[falla_b_id]), mecanico2_id, "Mecánico 2"
    )

    # Mecánico 1 termina su avance globalmente (sin especificar IDs de fallas)
    sol_post_m1 = await mantencion_service.terminar_avance(
        db_session,
        solicitud_id=sol.id,
        dto=TerminarAvanceDTO(comentario="Mecánico 1 terminó su parte"),
        mecanico_id=mecanico1_id,
        mecanico_nombre="Mecánico 1",
    )

    # El bus/OT DEBE permanecer en EN_REPARACION porque Mecánico 2 sigue en Falla B
    assert sol_post_m1.estado == "EN_REPARACION"

    # Falla B debe seguir con Mecánico 2 asignado
    detalle_b = next(d for d in sol_post_m1.detalles if d.id == falla_b_id)
    assert any(m.id == mecanico2_id for m in detalle_b.mecanicos_asignados)

    # Falla A no debe tener asignado a Mecánico 1
    detalle_a = next(d for d in sol_post_m1.detalles if d.id == falla_a_id)
    assert not any(m.id == mecanico1_id for m in detalle_a.mecanicos_asignados)

    # Ahora Mecánico 2 termina su avance
    sol_post_m2 = await mantencion_service.terminar_avance(
        db_session,
        solicitud_id=sol.id,
        dto=TerminarAvanceDTO(comentario="Mecánico 2 terminó"),
        mecanico_id=mecanico2_id,
        mecanico_nombre="Mecánico 2",
    )

    # Al no quedar ningún mecánico activo, la OT pasa a PENDIENTE
    assert sol_post_m2.estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_supervisor_crea_solicitud_marca_bus_en_taller(db_session, seed_test_data):
    """Verifica que una solicitud creada por la supervisora marque automáticamente al bus como en_taller = True."""
    from app.modules.buses.models.bus import Bus

    bus = Bus(n_bus="BUS-SUP-1", patente="SUP-001", is_active=True, en_taller=False)
    db_session.add(bus)
    await db_session.commit()
    await db_session.refresh(bus)

    supervisor = seed_test_data["supervisor"]
    falla1 = seed_test_data["falla1"]

    dto = SolicitudCreateDTO(
        bus_id=bus.id,
        n_bus=bus.n_bus,
        descripcion_general="Ingreso directo por supervisora",
        detalles=[SolicitudDetalleCreateDTO(falla_id=falla1.id, descripcion_personalizada="Revisión fosa 1")],
    )

    solicitud = await mantencion_service.create_solicitud(
        db_session,
        dto=dto,
        creador_id=supervisor.id,
        creador_nombre=supervisor.nombre_completo,
        creador_rol="SUPERVISOR",
    )

    assert solicitud.bus_id == bus.id
    assert solicitud.estado == "PENDIENTE"
    # El bus debe haber quedado con en_taller = True automáticamente
    await db_session.refresh(bus)
    assert bus.en_taller is True


@pytest.mark.asyncio
async def test_conductor_crea_solicitud_no_marca_bus_en_taller(db_session, seed_test_data):
    """Verifica que un reporte de conductor en ruta no fuerce indebidamente bus.en_taller a True."""
    from app.modules.buses.models.bus import Bus

    bus = Bus(n_bus="BUS-COND-1", patente="CND-001", is_active=True, en_taller=False)
    db_session.add(bus)
    await db_session.commit()
    await db_session.refresh(bus)

    conductor = seed_test_data["conductor"]
    falla1 = seed_test_data["falla1"]

    dto = SolicitudCreateDTO(
        bus_id=bus.id,
        n_bus=bus.n_bus,
        descripcion_general="Reporte en trayecto",
        detalles=[SolicitudDetalleCreateDTO(falla_id=falla1.id)],
    )

    solicitud = await mantencion_service.create_solicitud(
        db_session,
        dto=dto,
        creador_id=conductor.id,
        creador_nombre=conductor.nombre_completo,
        creador_rol="CONDUCTOR",
    )

    assert solicitud.bus_id == bus.id
    await db_session.refresh(bus)
    assert bus.en_taller is False


@pytest.mark.asyncio
async def test_supervisor_agrega_falla_sin_autoasignar(db_session, seed_test_data):
    """Verifica que cuando una supervisora agrega una falla a una OT, no se autoasigne como mecánico operativo."""
    from app.modules.mantencion.dtos.mantencion_dto import AgregarFallaDTO

    conductor = seed_test_data["conductor"]
    supervisor = seed_test_data["supervisor"]
    falla1 = seed_test_data["falla1"]
    falla2 = seed_test_data["falla2"]

    sol = await mantencion_service.create_solicitud(
        db_session,
        SolicitudCreateDTO(
            n_bus="BUS-SUP-FALLA",
            descripcion_general="OT inicial",
            detalles=[SolicitudDetalleCreateDTO(falla_id=falla1.id)],
        ),
        conductor.id,
    )

    # Supervisora agrega una segunda falla
    sol_actualizada = await mantencion_service.agregar_falla(
        db_session,
        solicitud_id=sol.id,
        mecanico_id=supervisor.id,
        dto=AgregarFallaDTO(falla_id=falla2.id, descripcion_personalizada="Detectada por supervisión"),
    )

    assert len(sol_actualizada.detalles) == 2
    falla_agregada = sol_actualizada.detalles[1]
    assert falla_agregada.falla_id == falla2.id
    # La supervisora NO debe quedar autoasignada a la avería
    assert len(falla_agregada.mecanicos_asignados) == 0

    # Bitácora registra a la supervisora
    comentarios = sol_actualizada.comentarios
    assert any("Supervisora" in c.comentario for c in comentarios)

