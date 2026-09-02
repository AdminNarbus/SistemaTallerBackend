import pytest


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Verifica la respuesta del endpoint raíz GET /."""
    response = await client.get("/")
    assert response.status_code == 200
    json_data = response.json()
    assert "Welcome to" in json_data["message"]
    assert json_data["health"] == "/api/v1/health"


@pytest.mark.asyncio
async def test_health_check_endpoint(client):
    """Verifica el estado de salud en GET /api/v1/health."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_db_endpoint_healthy(client):
    """Verifica el estado de conectividad a BD en GET /api/v1/health/db."""
    response = await client.get("/api/v1/health/db")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["status"] == "healthy"
    assert json_data["database"] == "connected"
