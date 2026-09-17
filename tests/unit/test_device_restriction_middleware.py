"""
test_device_restriction_middleware.py
====================================
Pruebas unitarias para DeviceRestrictionMiddleware bajo el patrón AAA.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from starlette.responses import PlainTextResponse

from app.core.config import settings
from app.core.middleware.device_restriction import DeviceRestrictionMiddleware


@pytest.fixture
def app_with_restriction():
    """Crea una aplicación FastAPI de prueba aislada con DeviceRestrictionMiddleware."""
    app = FastAPI()
    app.add_middleware(DeviceRestrictionMiddleware)

    @app.get("/api/v1/test-endpoint")
    async def sample_endpoint():
        return PlainTextResponse("success")

    @app.get("/health")
    async def health_endpoint():
        return PlainTextResponse("healthy")

    return app


@pytest.mark.asyncio
async def test_middleware_passthrough_when_disabled(app_with_restriction, monkeypatch):
    """Verifica que si las restricciones están inactivas, todo cliente accede normalmente (AAA)."""
    # Arrange
    monkeypatch.setattr(settings, "ENFORCE_MOBILE_ONLY", False)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", False)

    transport = ASGITransport(app=app_with_restriction)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Act
        res = await client.get("/api/v1/test-endpoint", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        # Assert
        assert res.status_code == 200
        assert res.text == "success"


@pytest.mark.asyncio
async def test_middleware_mobile_only_blocks_desktop(app_with_restriction, monkeypatch):
    """Verifica que con ENFORCE_MOBILE_ONLY=True se bloquee User-Agent de escritorio (AAA)."""
    # Arrange
    monkeypatch.setattr(settings, "ENFORCE_MOBILE_ONLY", True)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", False)

    transport = ASGITransport(app=app_with_restriction)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Act - Petición desde PC Desktop
        res = await client.get(
            "/api/v1/test-endpoint",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )

        # Assert
        assert res.status_code == 403
        assert "dispositivos móviles" in res.json()["detail"]


@pytest.mark.asyncio
async def test_middleware_mobile_only_allows_mobile_devices(app_with_restriction, monkeypatch):
    """Verifica que con ENFORCE_MOBILE_ONLY=True se permitan User-Agents móviles (AAA)."""
    # Arrange
    monkeypatch.setattr(settings, "ENFORCE_MOBILE_ONLY", True)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", False)

    transport = ASGITransport(app=app_with_restriction)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Act & Assert - Android
        res_android = await client.get(
            "/api/v1/test-endpoint",
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S908B) Mobile Safari/537.36"}
        )
        assert res_android.status_code == 200

        # Act & Assert - iPhone
        res_iphone = await client.get(
            "/api/v1/test-endpoint",
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) Mobile/15E148"}
        )
        assert res_iphone.status_code == 200


@pytest.mark.asyncio
async def test_middleware_origin_check(app_with_restriction, monkeypatch):
    """Verifica el control estricto de origen web autorizado con ENFORCE_ORIGIN_CHECK=True (AAA)."""
    # Arrange
    monkeypatch.setattr(settings, "ENFORCE_MOBILE_ONLY", False)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", True)
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["https://mitaller.narbus.cl", "http://localhost:5173"])

    transport = ASGITransport(app=app_with_restriction)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Act & Assert - Origen permitido
        res_ok = await client.get("/api/v1/test-endpoint", headers={"Origin": "https://mitaller.narbus.cl"})
        assert res_ok.status_code == 200

        # Act & Assert - Origen malicioso
        res_bad = await client.get("/api/v1/test-endpoint", headers={"Origin": "https://sitio-malicioso.com"})
        assert res_bad.status_code == 403
        assert "Origen web no autorizado" in res_bad.json()["detail"]


@pytest.mark.asyncio
async def test_middleware_bypass_with_app_client_secret(app_with_restriction, monkeypatch):
    """Verifica que el header X-App-Client-Key permita el bypass de seguridad a clientes autorizados (AAA)."""
    # Arrange
    monkeypatch.setattr(settings, "ENFORCE_MOBILE_ONLY", True)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", True)
    monkeypatch.setattr(settings, "APP_CLIENT_SECRET", "super-secret-key-2026")
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["https://mitaller.narbus.cl"])

    transport = ASGITransport(app=app_with_restriction)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Act - Petición desde Desktop y origen no listado, pero con la clave secreta
        res = await client.get(
            "/api/v1/test-endpoint",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Origin": "https://origen-externo.com",
                "X-App-Client-Key": "super-secret-key-2026",
            }
        )

        # Assert
        assert res.status_code == 200
        assert res.text == "success"


@pytest.mark.asyncio
async def test_middleware_excluded_paths(app_with_restriction, monkeypatch):
    """Verifica que rutas de salud estén siempre exentas de validación de dispositivo (AAA)."""
    # Arrange
    monkeypatch.setattr(settings, "ENFORCE_MOBILE_ONLY", True)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", True)

    transport = ASGITransport(app=app_with_restriction)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Act
        res = await client.get("/health", headers={"User-Agent": "HealthChecker/1.0 (Desktop Bot)"})

        # Assert
        assert res.status_code == 200
        assert res.text == "healthy"
