from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.api import deps
from app.core.exceptions import PermissionException
from app.modules.auth.dtos import UsuarioResponseDTO


def request(method, path="/api/v1/formularios/neumaticos"):
    return Request({"type": "http", "method": method, "path": path, "headers": []})


def visual_user():
    return UsuarioResponseDTO(id=10, username="consulta", rol="VISUAL", is_active=True)


@pytest.mark.parametrize("guard", [
    deps.require_supervisor_or_admin, deps.require_mecanico_or_admin,
    deps.require_conductor_or_admin, deps.require_conductor_or_supervisor_or_admin,
    deps.require_mecanico_or_supervisor_or_admin,
])
async def test_visual_role_guards_allow_read_and_reject_write(guard):
    user = visual_user()

    assert await guard(request("GET"), user) == user
    with pytest.raises(PermissionException):
        await guard(request("POST"), user)


async def test_global_visual_guard_blocks_optional_auth_write(monkeypatch):
    resolve = AsyncMock(return_value=visual_user())
    monkeypatch.setattr(deps, "get_current_user", resolve)

    with pytest.raises(PermissionException):
        await deps.enforce_visual_read_only(request("POST"), db=None, token="token")

    resolve.assert_awaited_once_with(db=None, token="token")


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/auth/usuarios"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/login/token"),
    ("POST", "/api/v1/auth/refresh"),
])
async def test_reads_and_session_operations_skip_global_guard(monkeypatch, method, path):
    resolve = AsyncMock()
    monkeypatch.setattr(deps, "get_current_user", resolve)

    await deps.enforce_visual_read_only(request(method, path), db=None, token="token")

    resolve.assert_not_awaited()
