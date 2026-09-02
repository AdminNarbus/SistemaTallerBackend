import pytest
from app.core.exceptions import NotFoundException
from app.modules.buses.models.bus import Bus
from app.modules.buses.services.bus_service import bus_service
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import SolicitudCreateDTO


@pytest.mark.asyncio
async def test_bus_service_search_and_get(db_session):
    """Prueba la búsqueda por prefijo, obtención por ID y por n_bus."""
    buses = [
        Bus(id=1, n_bus="10", patente="AA1010", marca="Mercedes", modelo="O500", is_active=True),
        Bus(id=2, n_bus="301", patente="BB3001", marca="Scania", modelo="K400", is_active=True),
        Bus(id=3, n_bus="339", patente="CC3399", marca="Volvo", modelo="B430", is_active=True),
        Bus(id=4, n_bus="342", patente="DD3422", marca="Scania", modelo="K440", is_active=True),
        Bus(id=5, n_bus="405", patente="EE4055", marca="Mercedes", modelo="O500", is_active=False),  # Inactivo
        Bus(id=6, n_bus="900", patente="FF9000", marca="Volvo", modelo="B450", is_active=True),
    ]
    for b in buses:
        db_session.add(b)
    await db_session.commit()

    # Búsqueda por prefijo "3"
    resultados_3 = await bus_service.buscar_sugerencias_buses(db_session, query="3")
    assert resultados_3 == ["301", "339", "342"]

    # Búsqueda de todos los activos (query vacío)
    todos = await bus_service.buscar_sugerencias_buses(db_session, query=None)
    assert todos == ["10", "301", "339", "342", "900"]

    # Obtener por ID
    bus_dto = await bus_service.get_bus_by_id(db_session, bus_id=3)
    assert bus_dto.n_bus == "339"
    assert bus_dto.patente == "CC3399"
    assert bus_dto.marca == "Volvo"

    # Obtener por n_bus
    bus_por_numero = await bus_service.get_bus_by_n_bus(db_session, n_bus="342")
    assert bus_por_numero.id == 4
    assert bus_por_numero.patente == "DD3422"

    # Error al buscar bus inexistente
    with pytest.raises(NotFoundException):
        await bus_service.get_bus_by_id(db_session, bus_id=999)

    with pytest.raises(NotFoundException):
        await bus_service.get_bus_by_n_bus(db_session, n_bus="9999")


@pytest.mark.asyncio
async def test_crear_solicitud_auto_asigna_bus_id(db_session, seed_test_data):
    """Prueba que al crear una solicitud de taller con n_bus='339', se asigna automáticamente bus_id."""
    conductor_id = seed_test_data["conductor"].id
    
    bus = Bus(id=7, n_bus="339", patente="GH3399", marca="Volvo", modelo="B430", is_active=True)
    db_session.add(bus)
    await db_session.commit()

    dto = SolicitudCreateDTO(
        n_bus="339",
        descripcion_general="Chequeo preventivo de motor",
    )
    solicitud = await mantencion_service.create_solicitud(db_session, dto, conductor_id)
    
    assert solicitud.id is not None
    assert solicitud.n_bus == "339"
    assert solicitud.bus_id == 7
    assert solicitud.bus_patente == "GH3399"
