import pytest
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import (
    SolicitudCreateDTO,
    SolicitudDetalleCreateDTO,
    TomarTrabajoDTO,
    LiberarTurnoDTO,
    FinalizarSolicitudDTO,
    ComentarioCreateDTO,
)
from app.core.exceptions import NotFoundException, BusinessRuleException


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
    assert solicitud.estado == "REPORTADO"
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
    sol_checked = await mantencion_service.check_detalle(db_session, solicitud.id, detalle_id, mecanico1_id, True)
    assert sol_checked.detalles[0].resuelto is True

    # 4. Liberar turno
    sol_liberada = await mantencion_service.liberar_turno(
        db_session, solicitud.id, mecanico1_id, LiberarTurnoDTO(comentario="Turno terminado, resta prueba en ruta")
    )
    assert sol_liberada.estado == "PENDIENTE_REASIGNACION"

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
