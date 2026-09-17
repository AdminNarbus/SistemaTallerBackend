import re
import logging
from typing import Set
from urllib.parse import urlparse
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)

# Expresión regular compilada de alta performance para detectar clientes móviles
MOBILE_USER_AGENT_PATTERN = re.compile(
    r"(android|iphone|ipod|ipad|iemobile|blackberry|opera mini|mobile|windows phone|silk/|kindle|webos)",
    re.IGNORECASE,
)

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
    1. Limita el tráfico a peticiones originadas desde el dominio web autorizado (CORS / Origin / Referer).
    2. Restringe el acceso a dispositivos móviles mediante inspección de User-Agent.
    3. Permite bypass mediante clave secreta compartida de aplicación (X-App-Client-Key).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. Peticiones OPTIONS (CORS preflight) y rutas de salud/docs exentas
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in EXCLUDED_PATHS or path.startswith("/uploads/"):
            return await call_next(request)

        # 2. Si no están activas las restricciones, continuar sin latencia añadida
        if not settings.ENFORCE_MOBILE_ONLY and not settings.ENFORCE_ORIGIN_CHECK:
            return await call_next(request)

        # 3. Bypass si se provee la clave secreta de cliente autorizada (X-App-Client-Key)
        client_key = request.headers.get("x-app-client-key")
        if settings.APP_CLIENT_SECRET and client_key == settings.APP_CLIENT_SECRET:
            return await call_next(request)

        # 4. Verificación de Origen Web (si ENFORCE_ORIGIN_CHECK está habilitado)
        if settings.ENFORCE_ORIGIN_CHECK:
            origin_header = request.headers.get("origin") or request.headers.get("referer") or ""
            if origin_header:
                origin_base = _extraer_origen_base(origin_header)
                allowed_origins = {
                    _extraer_origen_base(str(orig))
                    for orig in settings.BACKEND_CORS_ORIGINS
                }
                match_regex = False
                if settings.effective_cors_origin_regex:
                    match_regex = bool(re.match(settings.effective_cors_origin_regex, origin_base))

                if origin_base not in allowed_origins and not match_regex:
                    logger.warning(
                        "[SECURITY] Origen web denegado: '%s' no está en orígenes autorizados %s",
                        origin_base,
                        allowed_origins,
                    )
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Origen web no autorizado para consumir esta API."},
                    )

        # 5. Verificación de Dispositivo Móvil (si ENFORCE_MOBILE_ONLY está habilitado)
        if settings.ENFORCE_MOBILE_ONLY:
            user_agent = request.headers.get("user-agent", "")
            es_movil = bool(MOBILE_USER_AGENT_PATTERN.search(user_agent))
            if not es_movil:
                logger.warning(
                    "[SECURITY] Dispositivo denegado: User-Agent '%s' no es móvil en ruta %s",
                    user_agent,
                    path,
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Acceso restringido exclusivamente a dispositivos móviles autorizados."},
                )

        return await call_next(request)
