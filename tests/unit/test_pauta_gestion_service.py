from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.formularios.dtos.pauta_dto import PautaGestionUpdateDTO
from app.modules.formularios.services.formulario_pauta_service import FormularioPautaService


@pytest.mark.parametrize("puntos", [
    [{"item_id": 1, "estado": "OK"}, {"item_id": 1, "estado": None}],
    [{"item_id": 1, "estado": None, "observacion": "Revisión"}],
])
async def test_rechaza_cambios_antes_de_persistir(puntos):
    repo, db = AsyncMock(), AsyncMock()
    service = FormularioPautaService(repo)
    dto = PautaGestionUpdateDTO(puntos=puntos)

    with pytest.raises(BusinessRuleException):
        await service.actualizar_gestion(db, 1, dto, 4)

    repo.lock_solicitud.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_items_invalidos_no_escriben_parcialmente():
    repo, db = AsyncMock(), AsyncMock()
    repo.lock_solicitud.return_value = True
    repo.get_pauta_items_by_ids.return_value = {1}
    service = FormularioPautaService(repo)
    dto = PautaGestionUpdateDTO(puntos=[{"item_id": 1, "estado": "OK", "mecanico_id": 2},
                                      {"item_id": 99, "estado": None}])

    with pytest.raises(NotFoundException):
        await service.actualizar_gestion(db, 1, dto, 4)

    repo.eliminar_respuestas.assert_not_awaited()
    repo.upsert_pauta_respuestas.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_mecanicos_invalidos_no_escriben_parcialmente():
    repo, db = AsyncMock(), AsyncMock()
    repo.lock_solicitud.return_value = True
    repo.get_pauta_items_by_ids.return_value = {1, 2}
    repo.get_mecanicos_activos.return_value = {2: "Pedro Mecanico"}
    service = FormularioPautaService(repo)
    dto = PautaGestionUpdateDTO(puntos=[
        {"item_id": 1, "estado": "OK", "mecanico_id": 2},
        {"item_id": 2, "estado": "OK", "mecanico_id": 999},
    ])

    with pytest.raises(BusinessRuleException):
        await service.actualizar_gestion(db, 1, dto, 4)

    repo.eliminar_respuestas.assert_not_awaited()
    repo.upsert_pauta_respuestas.assert_not_awaited()
    db.commit.assert_not_awaited()
