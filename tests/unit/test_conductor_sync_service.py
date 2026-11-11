from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessRuleException, ConflictException
from app.modules.auth.dtos.conductor_sync_dto import ConductorExternoDTO
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.services import conductor_sync_service as module
from app.modules.auth.services.conductor_source import validar_conductores, preparar_conductores
from app.modules.auth.services import conductor_source


def conductor(**overrides):
    return {"rut": "12.345.678-k", "nombre": "Juan", "apellido": "Perez", "activo": True, **overrides}


@pytest.mark.parametrize("payload", [[], {}, [conductor(activo="false")],
    [conductor(rut="1234")], [conductor(), conductor(rut="12345678-K")],
    [conductor(), conductor(nombre=None)]])
def test_fuente_invalida_se_rechaza_completa(payload):
    with pytest.raises(BusinessRuleException):
        validar_conductores(payload)


def test_normaliza_rut_conserva_inactivos():
    resultado = validar_conductores([conductor(activo=False)])
    assert resultado[0].rut == "12345678-K"
    assert resultado[0].activo is False


@pytest.mark.parametrize("fecha,periodo", [
    ("2026-11-07T02:58:00+00:00", "2026-10"),
    ("2026-11-07T02:59:00+00:00", "2026-11"),
    ("2026-07-07T03:59:00+00:00", "2026-07"),
    ("2026-01-01T00:00:00+00:00", "2025-12"),
])
def test_periodo_horario_chile_verano_invierno(fecha, periodo):
    assert module.periodo_pendiente(datetime.fromisoformat(fecha)) == periodo


def test_actualiza_credenciales_sin_cambiar_rol_ni_telefono(monkeypatch):
    usuario = Usuario(username="12.345.678-k", password_hash="anterior", rol_id=3, telefono="123")
    monkeypatch.setattr(module, "verify_password", lambda password, hashed: False)
    monkeypatch.setattr(module, "get_password_hash", lambda password: f"hash:{password}")

    cambiado = module.aplicar_conductor(usuario, ConductorExternoDTO(**conductor(activo=False)))

    assert cambiado
    assert usuario.username == "12345678-K"
    assert usuario.password_hash == "hash:1234"
    assert not usuario.is_active
    assert usuario.rol_id == 3
    assert usuario.telefono == "123"


def test_apellido_nulo_de_fuente_se_guarda_vacio_para_neon(monkeypatch):
    usuario = Usuario(username="12345678-K", password_hash="hash", rol_id=3)
    monkeypatch.setattr(module, "verify_password", lambda password, hashed: True)
    module.aplicar_conductor(usuario, ConductorExternoDTO(**conductor(apellido=None)))
    assert usuario.apellido == ""


@pytest.fixture
def dependencias(monkeypatch):
    repo = SimpleNamespace(
        bloquear=AsyncMock(), obtener_ejecucion=AsyncMock(return_value=None),
        obtener_rol=AsyncMock(return_value=SimpleNamespace(id=3)),
        obtener_usuarios=AsyncMock(return_value={}), guardar=AsyncMock(),
    )
    fuente = AsyncMock(return_value=validar_conductores([conductor()]))
    monkeypatch.setattr(module, "repository", repo)
    monkeypatch.setattr(module, "obtener_conductores", fuente)
    monkeypatch.setattr(module, "get_password_hash", lambda password: f"hash:{password}")
    monkeypatch.setattr(module.conductor_sync_service, "_notificar", AsyncMock())
    return repo, fuente


async def test_crea_conductor_y_registra_mes_en_misma_transaccion(dependencias):
    repo, fuente = dependencias
    db = SimpleNamespace(add=lambda usuario: None, rollback=AsyncMock())

    resultado = await module.conductor_sync_service.sincronizar(db)

    assert resultado.creados == 1
    registro = repo.guardar.call_args.args[1]
    assert registro.resultado == resultado.model_dump()
    db.rollback.assert_not_awaited()


async def test_reintento_no_consulta_fuente_ni_modifica_usuarios(dependencias):
    repo, fuente = dependencias
    repo.obtener_ejecucion.return_value = SimpleNamespace(resultado={"periodo": "2026-10", "creados": 5})
    db = SimpleNamespace(rollback=AsyncMock())

    resultado = await module.conductor_sync_service.sincronizar(db)

    assert resultado.estado == "ya_ejecutado"
    assert resultado.creados == 5
    fuente.assert_not_awaited()
    repo.guardar.assert_not_awaited()


async def test_error_fuente_hace_rollback_sin_registrar_mes(dependencias):
    repo, fuente = dependencias
    fuente.side_effect = BusinessRuleException("Fuente inválida")
    db = SimpleNamespace(rollback=AsyncMock())

    with pytest.raises(BusinessRuleException):
        await module.conductor_sync_service.sincronizar(db)

    db.rollback.assert_awaited_once()
    repo.guardar.assert_not_awaited()


async def test_protege_cuenta_de_otro_rol(dependencias):
    repo, fuente = dependencias
    usuario = Usuario(username="12345678-K", password_hash="admin", rol_id=4, is_active=True)
    repo.obtener_usuarios.return_value = {usuario.username: usuario}
    fuente.return_value = validar_conductores([conductor(activo=False)])
    db = SimpleNamespace(rollback=AsyncMock())

    resultado = await module.conductor_sync_service.sincronizar(db)

    assert resultado.omitidos_otro_rol == 1
    assert usuario.password_hash == "admin"
    assert usuario.is_active


async def test_fallo_commit_no_notifica_y_hace_rollback(dependencias):
    repo, fuente = dependencias
    repo.guardar.side_effect = RuntimeError("commit falló")
    db = SimpleNamespace(add=lambda usuario: None, rollback=AsyncMock())

    with pytest.raises(RuntimeError):
        await module.conductor_sync_service.sincronizar(db)

    db.rollback.assert_awaited_once()
    module.conductor_sync_service._notificar.assert_not_awaited()


async def test_ejecucion_concurrente_no_consulta_fuente(dependencias):
    repo, fuente = dependencias
    repo.bloquear.side_effect = ConflictException("En curso")
    db = SimpleNamespace(rollback=AsyncMock())

    with pytest.raises(ConflictException):
        await module.conductor_sync_service.sincronizar(db)

    fuente.assert_not_awaited()


@pytest.mark.parametrize("estados", [(True, False), (False, True), (True, False, True)])
async def test_fuente_automatica_toma_ultimo_registro_y_campos(monkeypatch, estados):
    payload = [dict(conductor(activo=estado, nombre=f"Registro {index}"), id=index)
               for index, estado in enumerate(estados)]
    monkeypatch.setattr(conductor_source, "obtener_payload_conductores", AsyncMock(return_value=payload))

    resultado = await conductor_source.obtener_conductores()

    assert len(resultado) == 1
    assert resultado[0].activo is estados[-1]
    assert resultado[0].nombre == f"Registro {len(estados) - 1}"


@pytest.mark.parametrize("metodo", ["sincronizar", "sincronizar_ahora"])
async def test_automatico_y_manual_actualizan_estado_existentes(dependencias, monkeypatch, metodo):
    repo, fuente = dependencias
    activos = Usuario(username="12345678-K", rol_id=3, password_hash="hash", is_active=True)
    inactivos = Usuario(username="11222333-4", rol_id=3, password_hash="hash", is_active=False)
    repo.obtener_usuarios.return_value = {activos.username: activos, inactivos.username: inactivos}
    datos, _ = preparar_conductores([
        dict(conductor(activo=True), id=1), dict(conductor(activo=False), id=2),
        dict(conductor(rut="11222333-4", activo=True), id=3),
    ])
    fuente.return_value = datos
    monkeypatch.setattr(module, "verify_password", lambda plain, hashed: True)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    if metodo == "sincronizar":
        resultado = await module.conductor_sync_service.sincronizar(db)
    else:
        resultado = await module.conductor_sync_service.sincronizar_ahora(db, datos)

    assert not activos.is_active
    assert inactivos.is_active
    assert resultado.inhabilitados == 1
    assert resultado.habilitados == 1
    assert resultado.actualizados == 2
    if metodo == "sincronizar_ahora":
        db.commit.assert_awaited_once()
        repo.guardar.assert_not_awaited()


async def test_revision_completa_revierte_y_no_hace_commit(dependencias):
    repo, fuente = dependencias
    db = SimpleNamespace(add=lambda usuario: None, rollback=AsyncMock(), commit=AsyncMock())

    resultado = await module.conductor_sync_service.previsualizar_sincronizacion(db, fuente.return_value)

    assert resultado.creados == 1
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
