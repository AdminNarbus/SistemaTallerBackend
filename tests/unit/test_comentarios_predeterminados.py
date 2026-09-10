import pytest
import re
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import (
    SolicitudCreateDTO,
    SolicitudDetalleCreateDTO,
    TomarTrabajoDTO,
    AutoasignarFallasDTO,
    AsignarFallasSupervisoraDTO,
    TerminarAvanceDTO,
    ReportarRepuestoDTO,
    PautaBatchUpdateDTO,
    PautaRespuestaCreateDTO,
    FinalizarSolicitudDTO,
)


@pytest.mark.asyncio
async def test_flujo_comentarios_predeterminados_sin_ids(db_session, seed_test_data):
    """
    Verifica que:
    1. Iniciar OT (tomar_trabajo) añade comentario con nombre de mecánico y fallas de la OT.
    2. Autoasignar fallas incluye nombres legibles de averías y colaboradores (sin IDs numéricos).
    3. Asignación de supervisora incluye nombres legibles de fallas y participantes (sin IDs numéricos).
    4. check_detalle genera comentario automático de resolución o reapertura con nombre de falla.
    5. Terminar avance, reportar repuesto, pauta preventiva y cierre generan comentarios claros sin IDs.
    """
    conductor_id = seed_test_data["conductor"].id
    mecanico1_id = seed_test_data["mecanico1"].id
    mecanico2_id = seed_test_data["mecanico2"].id
    mecanico1_nom = seed_test_data["mecanico1"].nombre
    mecanico2_nom = seed_test_data["mecanico2"].nombre
    supervisor_id = seed_test_data["supervisor"].id
    supervisor_nom = seed_test_data["supervisor"].nombre
    falla1_id = seed_test_data["falla1"].id
    falla2_id = seed_test_data["falla2"].id
    falla1_nom = seed_test_data["falla1"].nombre
    falla2_nom = seed_test_data["falla2"].nombre

    # 1. Crear solicitud con 2 fallas
    dto_crear = SolicitudCreateDTO(
        n_bus="BUS-PREDET",
        descripcion_general="Prueba de comentarios automáticos sin IDs",
        detalles=[
            SolicitudDetalleCreateDTO(falla_id=falla1_id, descripcion_personalizada="Pastillas gastadas"),
            SolicitudDetalleCreateDTO(falla_id=falla2_id, descripcion_personalizada="Foco roto"),
        ],
    )
    solicitud = await mantencion_service.create_solicitud(db_session, dto_crear, conductor_id)
    det1_id = solicitud.detalles[0].id
    det2_id = solicitud.detalles[1].id

    # 2. Mecánico 1 toma la OT con Mecánico 2 como colaborador
    dto_tomar = TomarTrabajoDTO(
        colaboradores_ids=[mecanico2_id],
        comentario_inicial="Revisión general en fosa",
    )
    sol_tomada = await mantencion_service.tomar_trabajo(db_session, solicitud.id, mecanico1_id, dto_tomar)
    assert len(sol_tomada.comentarios) >= 1
    com_inicio = sol_tomada.comentarios[-1]
    assert com_inicio.tipo == "ASIGNACION"
    assert mecanico1_nom in com_inicio.comentario
    assert "inició los trabajos de esta OT atendiendo las fallas" in com_inicio.comentario
    assert mecanico2_nom in com_inicio.comentario
    assert "Revisión general en fosa" in com_inicio.comentario

    # 3. Check detalle: Mecánico 1 resuelve falla 1
    # check_detalle retorna DetalleUpdateDTO (Nivel 3 - DTO atómico)
    dto_check1 = await mantencion_service.check_detalle(db_session, solicitud.id, det1_id, mecanico1_id, True)
    assert dto_check1.detalle_id == det1_id
    assert dto_check1.resuelto is True
    # Para verificar el comentario de bitácora, obtenemos la solicitud completa
    sol_check1 = await mantencion_service.get_solicitud(db_session, solicitud.id)
    com_check = sol_check1.comentarios[-1]
    assert com_check.tipo == "RESOLUCION"
    assert mecanico1_nom in com_check.comentario
    assert "completó la reparación de la falla" in com_check.comentario
    assert "Pastillas gastadas" in com_check.comentario or falla1_nom in com_check.comentario

    # 4. Reportar falta de repuesto en falla 2
    dto_rep = ReportarRepuestoDTO(falta_repuesto=True, comentario="Esperando pedido de foco")
    # reportar_repuesto retorna DetalleUpdateDTO (Nivel 3 - DTO atómico)
    dto_rep_result = await mantencion_service.reportar_repuesto(db_session, solicitud.id, det2_id, dto_rep, mecanico1_id)
    assert dto_rep_result.falta_repuesto is True
    sol_rep = await mantencion_service.get_solicitud(db_session, solicitud.id)
    com_rep = sol_rep.comentarios[-1]
    assert com_rep.tipo == "FALTA_REPUESTO"
    assert mecanico1_nom in com_rep.comentario
    assert "FALTA DE REPUESTO" in com_rep.comentario
    assert "Foco roto" in com_rep.comentario or falla2_nom in com_rep.comentario
    assert "Esperando pedido de foco" in com_rep.comentario

    # 5. Reportar repuesto disponible para desbloquear
    dto_rep_ok = ReportarRepuestoDTO(falta_repuesto=False, comentario="Llegó repuesto a pañol")
    dto_rep_ok_result = await mantencion_service.reportar_repuesto(db_session, solicitud.id, det2_id, dto_rep_ok, mecanico1_id)
    assert dto_rep_ok_result.falta_repuesto is False
    sol_rep_ok = await mantencion_service.get_solicitud(db_session, solicitud.id)
    com_rep_ok = sol_rep_ok.comentarios[-1]
    assert com_rep_ok.tipo == "REPUESTO_DISPONIBLE"
    assert "REPUESTO DISPONIBLE" in com_rep_ok.comentario

    # 6. Autoasignar falla 2 con colaborador
    dto_auto = AutoasignarFallasDTO(
        detalles_ids=[det2_id],
        colaboradores_ids=[mecanico2_id],
        comentario="Instalando repuesto",
    )
    sol_auto = await mantencion_service.autoasignar_fallas(db_session, solicitud.id, dto_auto, mecanico1_id)
    com_auto = sol_auto.comentarios[-1]
    assert com_auto.tipo == "ASIGNACION"
    assert mecanico1_nom in com_auto.comentario
    assert "inició trabajo en las fallas" in com_auto.comentario
    assert mecanico2_nom in com_auto.comentario

    # 7. Supervisora asigna falla 1 a Mecánico 2
    dto_sup = AsignarFallasSupervisoraDTO(
        mecanico_id=mecanico2_id,
        detalles_ids=[det1_id],
        comentario="Revisión cruzada de frenos",
    )
    sol_sup = await mantencion_service.asignar_fallas_supervisora(db_session, solicitud.id, dto_sup, supervisor_id)
    com_sup = sol_sup.comentarios[-1]
    assert com_sup.tipo == "ASIGNACION"
    assert supervisor_nom in com_sup.comentario
    assert "asignó las fallas" in com_sup.comentario
    assert mecanico2_nom in com_sup.comentario

    # 8. Terminar avance en equipo
    dto_avance = TerminarAvanceDTO(detalles_ids=[det1_id, det2_id], comentario="Corte de turno mediodía")
    sol_avance = await mantencion_service.terminar_avance(db_session, solicitud.id, dto_avance, mecanico1_id)
    com_avance = sol_avance.comentarios[-1]
    assert com_avance.tipo == "ENTREGA_TURNO"
    assert "finalizó avance grupal" in com_avance.comentario
    assert "Corte de turno mediodía" in com_avance.comentario

    # 9. Resolver falla 2 y completar pauta preventiva
    # check_detalle retorna DetalleUpdateDTO (Nivel 3 - DTO atómico)
    dto_check2 = await mantencion_service.check_detalle(db_session, solicitud.id, det2_id, mecanico2_id, True)
    assert dto_check2.resuelto is True
    sol_check2 = await mantencion_service.get_solicitud(db_session, solicitud.id)
    assert sol_check2.comentarios[-1].tipo == "RESOLUCION"

    items_pauta = await mantencion_service.get_pauta_items(db_session)
    if items_pauta:
        dto_pauta = PautaBatchUpdateDTO(
            respuestas=[PautaRespuestaCreateDTO(item_id=it.id, estado="OK") for it in items_pauta]
        )
        await mantencion_service.guardar_respuestas_pauta(db_session, solicitud.id, dto_pauta, mecanico2_id)

    # 10. Finalizar solicitud
    dto_fin = FinalizarSolicitudDTO(
        comentario_cierre="Trabajos de frenos y luces 100% terminados",
        liberar_bus_taller=True,
    )
    sol_final = await mantencion_service.finalizar_solicitud(db_session, solicitud.id, mecanico2_id, dto_fin)
    com_cierre = sol_final.comentarios[-1]
    assert com_cierre.tipo == "CIERRE"
    assert mecanico2_nom in com_cierre.comentario
    assert "finalizó los trabajos de la OT y liberó el bus" in com_cierre.comentario
    assert "Trabajos de frenos y luces 100% terminados" in com_cierre.comentario

    # 11. VERIFICACIÓN CRÍTICA: Ningún comentario en la OT debe tener patrones de IDs numéricos técnicos
    patrones_prohibidos = [
        re.compile(r"\(IDs:\s*\[?[0-9]+", re.IGNORECASE),
        re.compile(r"al\s+mecánico\s*#[0-9]+", re.IGNORECASE),
        re.compile(r"falla\s*#[0-9]+", re.IGNORECASE),
        re.compile(r"colaboradores\s*\[[0-9]+", re.IGNORECASE),
        re.compile(r"Mecánico\s*#[0-9]+", re.IGNORECASE),
    ]

    for c in sol_final.comentarios:
        for patron in patrones_prohibidos:
            assert not patron.search(c.comentario), (
                f"Comentario contiene ID técnico prohibido: '{c.comentario}' (coincidencia con {patron.pattern})"
            )
