from types import SimpleNamespace

import pytest

from app.api.deps import require_current_user, require_supervisor_or_admin
from app.main import app


@pytest.mark.parametrize(
    "path",
    [
        "indicadores",
        "series/tendencia",
        "talleres/externos",
        "solicitudes",
        "buses/1/resumen",
        "buses/1/fallas?estado_falla=PENDIENTE",
        "buses/1/fallas/solicitudes?estado_falla=PENDIENTE&descripcion=Falla",
        "buses/1/cronologia",
        "buses/1/cronologia/detalles",
        "buses/1/cronologia/resumen",
        "filtros/buses",
    ],
)
async def test_every_dashboard_route_requires_identity(dashboard_client, path):
    app.dependency_overrides.pop(require_supervisor_or_admin)
    response = await dashboard_client.get(f"/api/v1/dashboard/{path}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    "role,expected", [("CONDUCTOR", 403), ("MECANICO", 403), ("ADMIN", 200), ("SUPERVISOR", 200)]
)
async def test_existing_role_authorization(dashboard_client, role, expected):
    app.dependency_overrides.pop(require_supervisor_or_admin)
    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(rol=role)
    response = await dashboard_client.get("/api/v1/dashboard/indicadores")
    assert response.status_code == expected, response.text
