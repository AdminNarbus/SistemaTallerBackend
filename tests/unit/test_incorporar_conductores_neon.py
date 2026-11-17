from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessRuleException
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.services import conductor_sync_service as service
from app.modules.auth.services.conductor_source import validar_conductores
from scripts.incorporar_conductores_neon import OpcionesCarga, preparar_carga, resolver_conexion


def test_admite_apellido_nulo_y_omite_solo_rut_invalido_inactivo():
    validos, omitidos = preparar_carga([
        {"id": 1, "rut": "12.345.678-k", "nombre": "Juan Perez", "apellido": None, "activo": True},
        {"id": 2, "rut": "SD", "nombre": "Sin datos", "activo": False},
    ])
    assert validos[0].rut == "12345678-K"
    assert validos[0].apellido is None
    assert omitidos == [{"id_fuente": 2, "motivo": "inactivo_con_rut_invalido"}]


@pytest.mark.parametrize("registro", [
    {"rut": "SD", "nombre": "Activo", "activo": True},
    {"rut": "12345678-K", "nombre": None, "activo": False},
    {"rut": "SD", "nombre": "Sin datos", "activo": "false"},
])
def test_no_omite_registros_activos_o_otros_errores(registro):
    with pytest.raises(BusinessRuleException):
        preparar_carga([registro])


def test_rut_duplicado_usa_ultimo_registro_incluso_si_desactiva():
    base = {"rut": "12345678-K", "nombre": "Juan", "activo": True}
    validos, omitidos = preparar_carga([
        {"id": 1, **base}, {"id": 2, **base, "activo": False},
        {"id": 3, **base, "rut": "11222333-4"},
    ])
    assert [item.rut for item in validos] == ["12345678-K", "11222333-4"]
    assert validos[0].activo is False
    assert omitidos == [{"id_fuente": 1, "reemplazado_por": 2, "motivo": "reemplazado_por_ultimo_registro"}]


def test_conexion_requiere_destino_explicito(monkeypatch):
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    with pytest.raises(BusinessRuleException):
        resolver_conexion(OpcionesCarga())


@pytest.mark.parametrize("raw", ["postgresql://user:pass@localhost/taller", "postgresql://user:pass@ep-test.neon.tech/otra"])
def test_rechaza_destino_ajeno(monkeypatch, raw):
    monkeypatch.setenv("NEON_DATABASE_URL", raw)
    with pytest.raises(BusinessRuleException):
        resolver_conexion(OpcionesCarga())


def test_ssl_obligatorio_y_no_ejecuta_archivo_legado(tmp_path, monkeypatch):
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    archivo = tmp_path / "legado.py"
    archivo.write_text("raise RuntimeError('NO EJECUTAR')\nURL='postgresql://user:pass@ep-test.neon.tech/taller?sslmode=require&channel_binding=require'", encoding="utf-8")

    url = resolver_conexion(OpcionesCarga(conexion_desde=archivo))

    assert url.drivername == "postgresql+asyncpg"
    assert dict(url.query) == {"ssl": "require"}


@pytest.fixture
def carga(monkeypatch):
    conductores = validar_conductores([
        {"rut": "12345678-K", "nombre": "Nuevo", "apellido": "Conductor", "activo": True},
        {"rut": "11222333-4", "nombre": "Existente", "apellido": "Cambiar", "activo": False},
    ])
    usuario = Usuario(username="11222333-4", nombre="Original", password_hash="conservar", is_active=True)
    from app.modules.auth.models.rol import Rol
    usuario.rol_rel = Rol(nombre="CONDUCTOR")
    repo = SimpleNamespace(bloquear=AsyncMock(), obtener_usuarios=AsyncMock(return_value={usuario.username: usuario}))
    monkeypatch.setattr(service, "repository", repo)
    aplicar = AsyncMock(return_value=(None, []))
    monkeypatch.setattr(service.conductor_sync_service, "_aplicar", aplicar)
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    return conductores, usuario, repo, aplicar, db


async def test_solo_incorpora_nuevos_sin_modificar_existentes(carga):
    conductores, usuario, repo, aplicar, db = carga

    resultado = await service.conductor_sync_service.incorporar_nuevos(db, conductores)

    assert resultado.creados == 1
    assert resultado.sin_cambios == 1
    assert aplicar.call_args.args[1] == [conductores[0]]
    assert usuario.nombre == "Original" and usuario.password_hash == "conservar" and usuario.is_active
    db.commit.assert_awaited_once()


async def test_revision_no_hace_commit(carga):
    conductores, usuario, repo, aplicar, db = carga
    resultado = await service.conductor_sync_service.previsualizar_altas(db, conductores)
    assert resultado.creados == 1
    db.commit.assert_not_awaited()
    aplicar.assert_not_awaited()


async def test_fallo_altas_revierte_transaccion(carga):
    conductores, usuario, repo, aplicar, db = carga
    aplicar.side_effect = RuntimeError("Fallo de inserción")
    with pytest.raises(RuntimeError):
        await service.conductor_sync_service.incorporar_nuevos(db, conductores)
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


async def test_repetir_carga_sin_nuevos_no_inserta(carga):
    conductores, usuario, repo, aplicar, db = carga
    resultado = await service.conductor_sync_service.incorporar_nuevos(db, [conductores[1]])
    assert resultado.creados == 0
    aplicar.assert_not_awaited()
