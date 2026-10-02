import logging
import re
from typing import Set
from urllib.parse import urlparse
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)

# Rutas públicas del sistema exentas de validación de dispositivo u origen
EXCLUDED_PATHS: Set[str] = {
    "/",
    "/health",
    f"{settings.API_V1_STR}/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    f"{settings.API_V1_STR}/openapi.json",
}


def _extraer_origen_base(url_o_dominio: str) -> str:
    """Normaliza y extrae esquema + host de una URL (ej: https://sub.ejemplo.com/ruta -> https://sub.ejemplo.com)."""
    if not url_o_dominio:
        return ""
    parsed = urlparse(url_o_dominio)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/").lower()
    return url_o_dominio.rstrip("/").lower()


class DeviceRestrictionMiddleware(BaseHTTPMiddleware):
    """
    Middleware de control de acceso perimetral:
    1. Limita el tráfico web al origen autorizado.
    2. Permite cualquier tipo de dispositivo.
    3. Mantiene bypass para clientes confiables configurados explícitamente.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. Peticiones OPTIONS (CORS preflight) y rutas de salud/docs exentas
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in EXCLUDED_PATHS or path.startswith("/uploads/"):
            return await call_next(request)

        # 2. Si no están activas las restricciones, continuar sin latencia añadida
        origin_check_enabled = settings.ENFORCE_ORIGIN_CHECK
        if not origin_check_enabled:
            return await call_next(request)

        # 3. Bypass si se provee la clave secreta de cliente autorizada (X-App-Client-Key)
        client_key = request.headers.get("x-app-client-key")
        if settings.APP_CLIENT_SECRET and client_key == settings.APP_CLIENT_SECRET:
            return await call_next(request)

        # 4. Verificación de Origen Web (si ENFORCE_ORIGIN_CHECK está habilitado)
        if origin_check_enabled:
            origin_header = request.headers.get("origin") or request.headers.get("referer") or ""
            origin_base = _extraer_origen_base(origin_header)
            allowed_origins = {
                _extraer_origen_base(orig) for orig in settings.effective_cors_origins
            }
            match_regex = bool(
                settings.effective_cors_origin_regex
                and re.match(settings.effective_cors_origin_regex, origin_base)
            )

            if not origin_base or (origin_base not in allowed_origins and not match_regex):
                logger.warning(
                    "[SECURITY] Origen web denegado: '%s' no está en orígenes autorizados %s",
                    origin_base or "<ausente>",
                    allowed_origins,
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Origen web no autorizado para consumir esta API."},
                )

        return await call_next(request)
