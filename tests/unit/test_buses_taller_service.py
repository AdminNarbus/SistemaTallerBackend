from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.buses.models.bus import Bus
from app.modules.taller.dtos.bus_mecanico_dto import AgregarFallaBusDTO
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.services.buses_taller_service import BusesTallerService, RegistroFallaBus


@pytest.mark.parametrize("bus, error", [
    (None, NotFoundException), (Bus(id=1, patente="BAJA", is_active=False), BusinessRuleException),
])
async def test_bus_no_disponible_no_crea_ot(bus, error):
    # Arrange
    repo = MagicMock()
    repo.get_bus_by_id = AsyncMock(return_value=bus)
    servicio = BusesTallerService(taller_repo=repo)
    actor = UsuarioResponseDTO(id=2, username="mecanico", rol="MECANICO", is_active=True)
    registro = RegistroFallaBus(1, actor, AgregarFallaBusDTO(nombre="Ruido"))
    db = AsyncMock()

    # Act / Assert
    with pytest.raises(error):
        await servicio.agregar_falla(db, registro)
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    repo.add_solicitud.assert_not_called()


async def test_bus_sin_ot_id_reutiliza_ot_por_numero():
    # Arrange
    repo = MagicMock()
    ot = TallerSolicitud(es_ot=True, id=20, n_bus="100", estado="LIBERADO")
    repo.get_solicitud_activa_por_bus = AsyncMock(side_effect=[None, ot])
    repo.flush = AsyncMock()
    servicio = BusesTallerService(taller_repo=repo)
    db = AsyncMock()
    bus = Bus(id=4, n_bus="100", patente="BUS100", is_active=True)

    # Act
    resultado = await servicio._resolver_ot(db, bus)

    # Assert
    assert resultado is ot
    assert ot.bus_id == 4
    assert repo.get_solicitud_activa_por_bus.await_args_list[0].args == (db, 4, "100")
    assert repo.get_solicitud_activa_por_bus.await_args_list[1].args == (db, None, "100")
    repo.add_solicitud.assert_not_called()


def test_payload_no_asigna_a_otro_mecanico():
    # Arrange
    actor = UsuarioResponseDTO(id=2, username="mecanico", rol="MECANICO", is_active=True)
    registro = RegistroFallaBus(1, actor, AgregarFallaBusDTO(nombre="Ruido", autoasignar=True))

    # Act
    payload = BusesTallerService()._payload_falla(registro)

    # Assert
    assert payload.autoasignar is True
    assert payload.descripcion_personalizada == "Ruido"
    assert payload.mecanico_asignado_id is None
    assert payload.mecanico_resolvio_id is None
