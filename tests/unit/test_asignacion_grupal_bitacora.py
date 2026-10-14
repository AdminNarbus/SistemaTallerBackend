from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import BusinessRuleException
from app.modules.auth.models.usuario import Usuario
from app.modules.taller.dtos import AsignarFallasSupervisoraDTO
from app.modules.taller.repository.taller_repository import TallerRepository
from app.modules.taller.services.cuadrilla_service import CuadrillaService


def contexto_asignacion():
    detalles = [
        SimpleNamespace(id=10, descripcion_personalizada="Sin A/C", asignaciones=[]),
        SimpleNamespace(id=20, descripcion_personalizada="Freno largo", asignaciones=[]),
    ]
    solicitud = SimpleNamespace(
        id=1, estado="EN_REPARACION", detalles=detalles,
        mecanicos=[], asignaciones_fallas=[], comentarios=[],
    )
    repo = MagicMock(spec=TallerRepository)
    repo.get_solicitud_operacional.return_value = solicitud
    repo.get_asignaciones_activas.return_value = []
    repo.get_presencias_activas_mecanicos.return_value = set()
    usuarios = {
        1: Usuario(id=1, nombre="Laura", apellido="Supervisora", is_active=True),
        2: Usuario(id=2, nombre="Ricardo", apellido="", is_active=True),
        3: Usuario(id=3, nombre="Cecil", apellido="", is_active=True),
    }
    return repo, usuarios


@pytest.mark.asyncio
@pytest.mark.parametrize("ya_asignado", [False, True])
async def test_asignacion_grupal_un_solo_comentario(ya_asignado):
    # Arrange: entradas repetidas y, opcionalmente, una asignación previa.
    repo, usuarios = contexto_asignacion()
    db = AsyncMock()
    if ya_asignado:
        repo.get_asignaciones_activas.return_value = [SimpleNamespace(mecanico_id=2, detalle_id=10)]
        repo.get_presencias_activas_mecanicos.return_value = {2}
    dto = AsignarFallasSupervisoraDTO(
        mecanicos_ids=[2, 3, 2], detalles_ids=[10, 20, 10], comentario="  Viendo en fosa  "
    )

    # Act: una sola petición asigna el grupo completo.
    with patch(
        "app.modules.auth.repository.user_repository.user_repository.get_by_ids_map",
        new=AsyncMock(return_value=usuarios),
    ), patch("app.modules.taller.services.cuadrilla_service.orm_to_solicitud_dto"):
        await CuadrillaService(repo).asignar_fallas_supervisora(db, 1, dto, 1)

    # Assert: cada pareja se crea una vez; la nota grupal aparece una sola vez.
    pares = {
        (call.args[1].mecanico_id, call.args[1].detalle_id)
        for call in repo.add_asignacion_falla.call_args_list
    }
    esperados = {(2, 10), (2, 20), (3, 10), (3, 20)}
    if ya_asignado:
        esperados.remove((2, 10))
    assert pares == esperados
    assert repo.add_asignacion_falla.call_count == len(esperados)
    assert repo.add_mecanico.call_count == (1 if ya_asignado else 2)
    repo.add_comentario.assert_called_once()
    comentario = repo.add_comentario.call_args.args[1]
    assert comentario.tipo == "ASIGNACION"
    assert comentario.usuario_id == 1
    assert comentario.comentario == "Asignación: Ricardo y Cecil — Sin A/C, Freno largo. Viendo en fosa"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mecanico_invalido_no_deja_asignacion_parcial():
    # Arrange: el segundo integrante está inactivo.
    repo, usuarios = contexto_asignacion()
    usuarios[3].is_active = False
    db = AsyncMock()
    dto = AsignarFallasSupervisoraDTO(mecanicos_ids=[2, 3], detalles_ids=[10])

    # Act / Assert: la validación del grupo ocurre antes de escribir.
    with patch(
        "app.modules.auth.repository.user_repository.user_repository.get_by_ids_map",
        new=AsyncMock(return_value=usuarios),
    ), pytest.raises(BusinessRuleException, match="inactivo"):
        await CuadrillaService(repo).asignar_fallas_supervisora(db, 1, dto, 1)
    repo.add_asignacion_falla.assert_not_called()
    repo.add_mecanico.assert_not_called()
    repo.add_comentario.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_asignacion_sin_mecanicos_se_rechaza():
    repo, _ = contexto_asignacion()
    dto = AsignarFallasSupervisoraDTO(detalles_ids=[10])
    with pytest.raises(BusinessRuleException, match="mecánico válido"):
        await CuadrillaService(repo).asignar_fallas_supervisora(AsyncMock(), 1, dto, 1)
    repo.add_comentario.assert_not_called()


def test_asignacion_singular_retrocompatible():
    dto = AsignarFallasSupervisoraDTO(mecanico_id=2, detalles_ids=[10])
    assert dto.effective_mecanicos_ids == [2]
