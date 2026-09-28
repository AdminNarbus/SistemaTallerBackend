import pytest
from app.modules.taller.models.pauta_taller import PautaTallerItem
from app.modules.formularios.dtos import (
    FormularioMantencionCreateDTO,
    PautaBatchUpdateDTO,
    PautaRespuestaCreateDTO,
    ReporteNeumaticoCreateDTO,
)
from app.modules.formularios.repository import pauta_repository, neumatico_repository
from app.modules.formularios.services import (
    formulario_taller_service,
    formulario_pauta_service,
    formulario_neumatico_service,
)


async def _sembrar_pauta_items(db_session):
    """Siembra 11 ítems estándar de pauta de taller para pruebas unitarias."""
    items = [
        PautaTallerItem(id=i, categoria="General", item=f"Ítem Pauta {i}", orden=i, is_active=True)
        for i in range(1, 12)
    ]
    db_session.add_all(items)
    await db_session.commit()
    return items


@pytest.mark.asyncio
async def test_formularios_pauta_repository_items(db_session):
    """Verifica que pauta_repository consulte el catálogo maestro de ítems."""
    await _sembrar_pauta_items(db_session)
    items = await pauta_repository.get_pauta_items(db_session)
    assert len(items) >= 11
    assert any(it.item for it in items)


@pytest.mark.asyncio
async def test_formularios_pauta_service_resumen(db_session, seed_test_data):
    """Verifica que formulario_pauta_service calcule el resumen de pauta para una solicitud."""
    await _sembrar_pauta_items(db_session)
    conductor = seed_test_data["conductor"]

    dto = FormularioMantencionCreateDTO(
        n_bus="BUS-PAUTA-TEST",
        descripcion_general="Prueba de pauta preventiva en módulo formularios",
    )
    solicitud = await formulario_taller_service.procesar_formulario_ingreso(
        db=db_session,
        dto=dto,
        creador_id=conductor.id,
    )

    resumen = await formulario_pauta_service.get_pauta_resumen(db_session, solicitud.id)
    assert resumen.total_items >= 11
    assert isinstance(resumen.respondidos, int)
    assert isinstance(resumen.completado, bool)
    assert resumen.respondidos == 0
    assert resumen.completado is False


@pytest.mark.asyncio
async def test_formularios_taller_service_creacion(db_session, seed_test_data):
    """Verifica que formulario_taller_service procese una solicitud de ingreso."""
    conductor = seed_test_data["conductor"]

    dto = FormularioMantencionCreateDTO(
        n_bus="BUS-TEST-100",
        descripcion_general="Ingreso preventivo vía módulo formularios",
    )

    solicitud = await formulario_taller_service.procesar_formulario_ingreso(
        db=db_session,
        dto=dto,
        creador_id=conductor.id,
        creador_nombre=conductor.nombre_completo,
        creador_rol="CONDUCTOR",
    )

    assert solicitud.id is not None
    assert solicitud.n_bus == "BUS-TEST-100"
    assert solicitud.descripcion_general == "Ingreso preventivo vía módulo formularios"


@pytest.mark.asyncio
async def test_formularios_pauta_service_guardar_respuestas(db_session, seed_test_data):
    """Verifica que formulario_pauta_service guarde respuestas y actualice el resumen."""
    items = await _sembrar_pauta_items(db_session)
    conductor = seed_test_data["conductor"]
    mecanico = seed_test_data["mecanico1"]

    dto = FormularioMantencionCreateDTO(
        n_bus="BUS-TEST-200",
        descripcion_general="Prueba de guardado pauta",
    )
    solicitud = await formulario_taller_service.procesar_formulario_ingreso(
        db=db_session,
        dto=dto,
        creador_id=conductor.id,
    )

    batch_dto = PautaBatchUpdateDTO(
        respuestas=[
            PautaRespuestaCreateDTO(item_id=1, estado="BUENO", observacion="OK"),
            PautaRespuestaCreateDTO(item_id=2, estado="DEFECTO", observacion="Requiere cambio"),
        ]
    )
    resumen = await formulario_pauta_service.guardar_respuestas_pauta(
        db=db_session,
        solicitud_id=solicitud.id,
        dto=batch_dto,
        mecanico_id=mecanico.id,
    )

    assert resumen.total_items >= 11
    assert resumen.respondidos == 2
    assert resumen.items_con_defecto == 1
    assert resumen.pendientes == resumen.total_items - 2


@pytest.mark.asyncio
async def test_formularios_neumatico_service_estado():
    """Verifica el estado de disponibilidad del formulario de neumáticos."""
    status_dto = await formulario_neumatico_service.obtener_estado_formulario()
    assert status_dto.status == "success"


@pytest.mark.asyncio
async def test_formularios_api_endpoints(client, seed_test_data, auth_headers_mecanico1):
    """Verifica el acceso HTTP a los nuevos endpoints unificados bajo /api/v1/formularios."""
    # 1. Catálogo de pauta preventiva
    resp = await client.get("/api/v1/formularios/pauta/items", headers=auth_headers_mecanico1)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 2. Estado de formulario de neumáticos
    resp_neum = await client.get("/api/v1/formularios/neumaticos/estado")
    assert resp_neum.status_code == 200
    assert resp_neum.json().get("status") == "success"


