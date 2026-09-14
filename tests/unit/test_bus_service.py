from unittest.mock import AsyncMock, MagicMock
import pytest
from app.core.exceptions import NotFoundException
from app.modules.buses.models.bus import Bus
from app.modules.buses.repository.bus_repository import BusRepository
from app.modules.buses.services.bus_service import (
    BusService,
    bus_service,
    es_bus_operativo_taller,
)
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.dtos.mantencion_dto import SolicitudCreateDTO


# ==============================================================================
# 1. Pruebas Unitarias Puras: Reglas de Dominio (es_bus_operativo_taller)
# ==============================================================================

def test_es_bus_operativo_taller_valores_limite_y_casos_borde():
    """Valida la regla de negocio del rango operativo de taller (200 <= n_bus < 900)."""
    # Arrange & Assert
    assert es_bus_operativo_taller("199") is False
    assert es_bus_operativo_taller("200") is True
    assert es_bus_operativo_taller("339") is True
    assert es_bus_operativo_taller("899") is True
    assert es_bus_operativo_taller("900") is False
    assert es_bus_operativo_taller("950") is False

    # Con espacios en blanco
    assert es_bus_operativo_taller(" 339 ") is True

    # Entradas no numéricas o inválidas
    assert es_bus_operativo_taller("AUX-01") is False
    assert es_bus_operativo_taller("") is False
    assert es_bus_operativo_taller(None) is False


# ==============================================================================
# 2. Pruebas Unitarias Puras con Mocks (Aislamiento de Persistencia)
# ==============================================================================

@pytest.mark.asyncio
async def test_buscar_sugerencias_buses_unitario_con_mock():
    """Evalúa buscar_sugerencias_buses aislando el repositorio con AsyncMock."""
    # Arrange
    mock_repo = AsyncMock(spec=BusRepository)
    mock_repo.buscar_por_prefijo.return_value = [
        Bus(id=1, n_bus="10", patente="AA1010", is_active=True, en_taller=False),
        Bus(id=2, n_bus="342", patente="DD3422", is_active=True, en_taller=False),
        Bus(id=3, n_bus="301", patente="BB3001", is_active=True, en_taller=False),
        Bus(id=4, n_bus="900", patente="FF9000", is_active=True, en_taller=False),
    ]
    service = BusService(repository=mock_repo)
    mock_db = MagicMock()

    # Act
    resultados = await service.buscar_sugerencias_buses(
        mock_db, query="3", solo_flota_taller=True
    )

    # Assert
    mock_repo.buscar_por_prefijo.assert_awaited_once_with(
        mock_db, prefix="3", solo_activos=True, limit=None
    )
    # Excluye 10 (<200) y 900 (>=900), y ordena numéricamente: [301, 342]
    assert [b.n_bus for b in resultados] == ["301", "342"]
    assert resultados[0].id == 3
    assert resultados[1].id == 2


@pytest.mark.asyncio
async def test_get_bus_by_id_unitario_mock_not_found():
    """Valida el lanzamiento de NotFoundException al buscar por ID inexistente."""
    # Arrange
    mock_repo = AsyncMock(spec=BusRepository)
    mock_repo.get_by_id.return_value = None
    service = BusService(repository=mock_repo)
    mock_db = MagicMock()

    # Act & Assert
    with pytest.raises(NotFoundException) as exc_info:
        await service.get_bus_by_id(mock_db, bus_id=999)
    assert "999" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_bus_by_n_bus_unitario_mock_not_found():
    """Valida el lanzamiento de NotFoundException al buscar por n_bus inexistente."""
    # Arrange
    mock_repo = AsyncMock(spec=BusRepository)
    mock_repo.get_by_n_bus.return_value = None
    service = BusService(repository=mock_repo)
    mock_db = MagicMock()

    # Act & Assert
    with pytest.raises(NotFoundException) as exc_info:
        await service.get_bus_by_n_bus(mock_db, n_bus="999")
    assert "999" in str(exc_info.value)


@pytest.mark.asyncio
async def test_actualizar_en_taller_unitario_con_mock():
    """Valida la actualización atómica y commit transaccional en el servicio."""
    # Arrange
    bus_mock = Bus(id=5, n_bus="339", patente="CC3399", is_active=True, en_taller=True)
    mock_repo = AsyncMock(spec=BusRepository)
    mock_repo.update_en_taller_directo.return_value = bus_mock
    service = BusService(repository=mock_repo)
    mock_db = AsyncMock()

    # Act
    resultado = await service.actualizar_en_taller(
        mock_db, bus_id=5, en_taller=True, motivo="Ingreso taller"
    )

    # Assert
    mock_repo.update_en_taller_directo.assert_awaited_once_with(
        mock_db, bus_id=5, en_taller=True
    )
    mock_db.commit.assert_awaited_once()
    assert resultado.id == 5
    assert resultado.en_taller is True


@pytest.mark.asyncio
async def test_listar_buses_unitario_con_paginacion():
    """Verifica que listar_buses delegue parámetros de paginación al repositorio."""
    # Arrange
    mock_repo = AsyncMock(spec=BusRepository)
    mock_repo.get_all.return_value = [
        Bus(id=1, n_bus="301", patente="AA11", marca="Scania", is_active=True, en_taller=False),
        Bus(id=2, n_bus="302", patente="BB22", marca="Volvo", is_active=True, en_taller=False),
    ]
    service = BusService(repository=mock_repo)
    mock_db = MagicMock()

    # Act
    resultado = await service.listar_buses(
        mock_db, solo_activos=True, solo_flota_taller=True, skip=10, limit=20
    )

    # Assert
    mock_repo.get_all.assert_awaited_once_with(
        mock_db, solo_activos=True, skip=10, limit=20
    )
    assert len(resultado) == 2
    assert resultado[0].n_bus == "301"


# ==============================================================================
# 3. Pruebas de Integración con Base de Datos de Prueba (db_session)
# ==============================================================================

@pytest.mark.asyncio
async def test_bus_service_search_and_get_integration(db_session):
    """Prueba integral de búsqueda por prefijo, obtención por ID y por n_bus en BD."""
    buses = [
        Bus(id=1, n_bus="10", patente="AA1010", marca="Mercedes", modelo="O500", is_active=True),
        Bus(id=2, n_bus="301", patente="BB3001", marca="Scania", modelo="K400", is_active=True),
        Bus(id=3, n_bus="339", patente="CC3399", marca="Volvo", modelo="B430", is_active=True),
        Bus(id=4, n_bus="342", patente="DD3422", marca="Scania", modelo="K440", is_active=True),
        Bus(id=5, n_bus="405", patente="EE4055", marca="Mercedes", modelo="O500", is_active=False),
        Bus(id=6, n_bus="900", patente="FF9000", marca="Volvo", modelo="B450", is_active=True),
    ]
    for b in buses:
        db_session.add(b)
    await db_session.commit()

    # Búsqueda por prefijo "3"
    resultados_3 = await bus_service.buscar_sugerencias_buses(db_session, query="3")
    assert [b.n_bus for b in resultados_3] == ["301", "339", "342"]
    assert resultados_3[0].id == 2
    assert resultados_3[0].patente == "BB3001"

    # Búsqueda de todos los activos en catálogo de taller (excluye 10 < 200 y 900 >= 900)
    todos_taller = await bus_service.buscar_sugerencias_buses(db_session, query=None)
    assert [b.n_bus for b in todos_taller] == ["301", "339", "342"]

    # Búsqueda sin filtro de flota (todos los activos en BD)
    todos_completo = await bus_service.buscar_sugerencias_buses(db_session, query=None, solo_flota_taller=False)
    assert [b.n_bus for b in todos_completo] == ["10", "301", "339", "342", "900"]

    # Obtener por ID
    bus_dto = await bus_service.get_bus_by_id(db_session, bus_id=3)
    assert bus_dto.n_bus == "339"
    assert bus_dto.patente == "CC3399"
    assert bus_dto.marca == "Volvo"
    assert bus_dto.en_taller is False

    # Actualizar estado en_taller
    bus_actualizado = await bus_service.actualizar_en_taller(
        db_session, bus_id=3, en_taller=True, motivo="Mantenimiento preventivo"
    )
    assert bus_actualizado.en_taller is True

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
