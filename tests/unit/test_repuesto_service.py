"""Reglas de autorización de repuestos con persistencia aislada."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.core.exceptions import PermissionException
from app.modules.taller.services.repuesto_service import repuesto_service


@pytest.mark.parametrize("activo,rol_real,rol_sesion,permitido", [
    (True, "SUPERVISOR", "SUPERVISOR", True),
    (True, "ADMIN", "ADMIN", True),
    (True, "MECANICO", "MECANICO", True),
    (False, "SUPERVISOR", "SUPERVISOR", False),
    (True, "MECANICO", "SUPERVISOR", False),
    (True, "CONDUCTOR", "CONDUCTOR", False),
    (True, "VISUAL", "VISUAL", False),
])
async def test_verificar_actor(activo, rol_real, rol_sesion, permitido):
    actor = SimpleNamespace(id=1, rol=rol_sesion)
    usuario = SimpleNamespace(is_active=activo, rol_rel=SimpleNamespace(nombre=rol_real))
    with patch("app.modules.taller.services.repuesto_service.taller_repository.get_usuario_by_id",
        new=AsyncMock(return_value=usuario)):
        if permitido:
            await repuesto_service._verificar_actor(None, actor)
        else:
            with pytest.raises(PermissionException):
                await repuesto_service._verificar_actor(None, actor)
