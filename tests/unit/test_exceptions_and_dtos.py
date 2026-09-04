import pytest
from pydantic import ValidationError
from app.core.exceptions import (
    NarbusException,
    NotFoundException,
    ConflictException,
    BusinessRuleException,
    PermissionException,
    _error_body,
)
from app.modules.mantencion.dtos.mantencion_dto import SolicitudCreateDTO


def test_domain_exceptions_status_codes_and_payload():
    """Verifica códigos HTTP y estructuras de excepciones de dominio."""
    nf = NotFoundException("Recurso 123 no existe", detail={"id": 123})
    assert nf.status_code == 404
    assert nf.error_code == "NOT_FOUND"
    assert nf.message == "Recurso 123 no existe"
    assert nf.detail == {"id": 123}

    conf = ConflictException("Duplicado")
    assert conf.status_code == 409
    assert conf.error_code == "CONFLICT"

    br = BusinessRuleException("Falla no resuelta")
    assert br.status_code == 422
    assert br.error_code == "BUSINESS_RULE_VIOLATION"

    perm = PermissionException("Acceso no autorizado")
    assert perm.status_code == 403
    assert perm.error_code == "FORBIDDEN"


def test_error_body_structure():
    """Verifica el formato del cuerpo de error estandarizado JSON."""
    body = _error_body("TEST_CODE", "Mensaje de prueba", detail="Detalle extra")
    assert body == {
        "error": {
            "code": "TEST_CODE",
            "message": "Mensaje de prueba",
            "detail": "Detalle extra",
        }
    }


def test_dto_pydantic_validation():
    """Prueba las validaciones Pydantic para los DTOs de entrada."""
    # Válido
    valid_dto = SolicitudCreateDTO(n_bus="BUS-001", descripcion_general="Falla de frenos")
    assert valid_dto.n_bus == "BUS-001"

    # Inválido por campo requerido faltante (n_bus es obligatorio)
    with pytest.raises(ValidationError):
        SolicitudCreateDTO()
