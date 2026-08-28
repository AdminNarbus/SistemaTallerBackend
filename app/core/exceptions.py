"""
exceptions.py
=============
Excepciones de dominio centralizadas y handlers globales para FastAPI.

Uso en repositorios/servicios:
    from app.core.exceptions import NotFoundException, BusinessRuleException, ConflictException

Los handlers se registran en app/main.py vía app.add_exception_handler().
"""
import logging
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Excepciones de dominio
# ─────────────────────────────────────────────────────────

class NarbusException(Exception):
    """Clase base para todas las excepciones de dominio de Narbus.
    No se lanza directamente; usar las subclases semánticas.
    """
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail=None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class NotFoundException(NarbusException):
    """Recurso no encontrado en la base de datos. → HTTP 404"""
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictException(NarbusException):
    """Conflicto con el estado actual del recurso (ej: registro duplicado). → HTTP 409"""
    status_code = 409
    error_code = "CONFLICT"


class BusinessRuleException(NarbusException):
    """Violación de una regla de negocio (ej: mecánico no asignado, solicitud ya finalizada). → HTTP 422"""
    status_code = 422
    error_code = "BUSINESS_RULE_VIOLATION"


class PermissionException(NarbusException):
    """Acción no permitida para el rol del usuario autenticado. → HTTP 403"""
    status_code = 403
    error_code = "FORBIDDEN"


# ─────────────────────────────────────────────────────────
# Formato de respuesta de error unificado
# ─────────────────────────────────────────────────────────

def _error_body(code: str, message: str, detail=None) -> dict:
    """Construye el cuerpo JSON de error estandarizado para toda la API."""
    return {
        "error": {
            "code": code,
            "message": message,
            "detail": detail,
        }
    }


# ─────────────────────────────────────────────────────────
# Handlers globales
# ─────────────────────────────────────────────────────────

async def narbus_exception_handler(request: Request, exc: NarbusException) -> JSONResponse:
    """
    Maneja todas las subclases de NarbusException (NotFoundException,
    BusinessRuleException, ConflictException, PermissionException).
    """
    logger.warning(
        "[NARBUS_EXCEPTION] %s %s → %s: %s",
        request.method,
        request.url.path,
        exc.error_code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.error_code, exc.message, exc.detail),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Re-formatea HTTPException de FastAPI/Starlette al formato de error unificado.
    Preserva el header WWW-Authenticate en respuestas 401 para cumplir con OAuth2 Bearer.
    """
    headers = {}
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        headers["WWW-Authenticate"] = "Bearer"

    logger.warning(
        "[HTTP_EXCEPTION] %s %s → HTTP %s: %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body("HTTP_ERROR", str(exc.detail) if exc.detail else "Error HTTP"),
        headers=headers or None,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Re-formatea los errores de validación de Pydantic (RequestValidationError)
    al formato de error unificado, incluyendo la lista de campos inválidos.
    """
    errors = [
        {"field": list(e["loc"]), "msg": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body(
            "VALIDATION_ERROR",
            "Error de validación en los datos enviados.",
            errors,
        ),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler de último recurso: captura cualquier excepción no prevista,
    registra el traceback completo en el logger y devuelve un 500 seguro
    sin exponer detalles internos al cliente.
    """
    logger.exception(
        "[UNHANDLED ERROR] %s %s → %s: %s",
        request.method,
        request.url,
        type(exc).__name__,
        exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(
            "INTERNAL_ERROR",
            "Error interno del servidor. Por favor, intente más tarde.",
        ),
    )
