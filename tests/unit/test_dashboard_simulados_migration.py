"""Contrato de importación: no confundir IDs de maestros ni perder relaciones."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

PATH = Path(__file__).resolve().parents[2] / "alembic/versions/032_dashboard_simulados_local.py"
spec = importlib.util.spec_from_file_location("dashboard_seed_migration", PATH)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_snapshot_relationships_and_counts():
    # Arrange: IDs locales deliberadamente distintos de los de la fuente.
    data = migration.read_snapshot()
    maps = {key: {r["id"]: r["id"] + 2000 for r in data["referencias"][name]}
            for key, name in (("bus_id", "buses"), ("ciudad_id", "ciudades"), ("rol_id", "roles"))}

    # Act
    rows = migration.prepare_rows(data, maps)

    # Assert
    assert len(rows["taller_solicitudes"]) == 409
    assert len(rows["taller_solicitud_detalles"]) == 1253
    assert len(rows["taller_solicitud_mecanicos"]) == 1445
    assert len(rows["taller_asignacion_fallas"]) == 1451
    assert len(rows["taller_resultado_ubicaciones"]) == 390
    for source, row in zip(data["tablas"]["taller_solicitudes"], rows["taller_solicitudes"]):
        assert row["bus_id"] == maps["bus_id"][source["bus_id"]]
        assert row["fecha_creacion"] == source["fecha_creacion"]
        assert row["estado"] == source["estado"]
    ids = {name: {r["id"] for r in entries} for name, entries in rows.items()
           if name != "taller_resultado_operaciones"}
    assert all(r["solicitud_id"] in ids["taller_solicitudes"] for r in rows["taller_solicitud_detalles"])
    assert all(r["detalle_id"] in ids["taller_solicitud_detalles"] for r in rows["taller_asignacion_fallas"])
    assert all(r["evento_id"] in ids["taller_falla_eventos"] for r in rows["taller_resultado_ubicaciones"])
    assert all(r["mecanico_id"] in ids["usuarios"] for r in rows["taller_asignacion_fallas"])
    assert all(not r["is_active"] and r["password_hash"].startswith("!") for r in rows["usuarios"])


def test_active_crews_with_different_dates_are_rejected():
    rows = [{"id": i, "solicitud_id": 1, "mecanico_id": 1, "is_activo": True,
             "fecha_asignacion": f"2026-10-{i:02}"} for i in (1, 2)]
    with pytest.raises(RuntimeError, match="no es un duplicado exacto"):
        migration.deduplicate_active_crews(rows)


def test_default_upgrade_does_not_even_connect(monkeypatch):
    bind = Mock()
    monkeypatch.setattr(migration, "context", SimpleNamespace(get_x_argument=lambda **_: {}))
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=bind))
    migration.upgrade()
    bind.assert_not_called()


@pytest.mark.parametrize("host", ["db.neon.tech", "192.168.1.2", None])
def test_remote_hosts_rejected(host):
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"),
                           engine=SimpleNamespace(url=SimpleNamespace(host=host)))
    with pytest.raises(RuntimeError, match="loopback"):
        migration.require_local(bind)
