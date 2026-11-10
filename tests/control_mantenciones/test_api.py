"""Contratos HTTP y permisos sin iniciar ni sembrar la aplicación operativa."""

from io import BytesIO

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook
import pytest
from sqlalchemy import select, func

from app.api.deps import require_current_user
from app.core.database import get_db
from app.core.exceptions import NarbusException, narbus_exception_handler
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.control_mantenciones.api.router import router
from app.modules.control_mantenciones.models.entities import ControlEvento


@pytest.fixture
async def api_control(sesiones):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/control-mantenciones")
    app.add_exception_handler(NarbusException, narbus_exception_handler)

    async def sesion():
        async with sesiones() as db:
            yield db

    async def usuario():
        return UsuarioResponseDTO(
            id=900001,
            username="control_test",
            nombre_completo="Prueba",
            rol="ADMIN",
            is_active=True,
        )

    app.dependency_overrides[get_db] = sesion
    app.dependency_overrides[require_current_user] = usuario
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield app, client


async def test_api_permisos_contratos_y_exportacion(api_control):
    app, client = api_control
    base = "/api/v1/control-mantenciones"
    assert (await client.get(base + "/panel")).status_code == 200
    assert (await client.get(base + "/panel?limit=101")).status_code == 422
    response = await client.post(
        base + "/mantenciones",
        json={"bus_id": 900001, "fecha": "2026-01-01", "kilometraje": "100000"},
    )
    assert response.status_code == 201, response.text
    identificador = response.json()["datos"]["id"]
    assert (
        await client.post(
            base + f"/mantenciones/{identificador}/comentarios",
            json={"comentario": "Revisión completada"},
        )
    ).status_code == 201
    assert (await client.get(base + f"/eventos?mantencion_id={identificador}")).json()[
        "total"
    ] == 2
    assert (await client.get(base + "/buses/900001/grafico")).status_code == 200
    assert (
        (await client.get(base + "/exportaciones"))
        .headers["content-type"]
        .startswith("application/vnd.openxmlformats")
    )

    async def mecanico():
        return UsuarioResponseDTO(
            id=900001,
            username="control_test",
            nombre_completo="Prueba",
            rol="MECANICO",
            is_active=True,
        )

    app.dependency_overrides[require_current_user] = mecanico
    assert (await client.get(base + "/panel")).status_code == 403

    async def anonimo():
        return None

    app.dependency_overrides.pop(require_current_user)
    assert (await client.get(base + "/panel")).status_code == 401


async def test_api_excel_no_guarda_y_confirmacion(api_control, sesiones):
    app, client = api_control
    base = "/api/v1/control-mantenciones"
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Query result"
    hoja.append(["n_bus", "fecha", "hora", "odometro"])
    hoja.append([354, "2026-01-01", "inválida", 100000])
    buffer = BytesIO()
    libro.save(buffer)
    respuesta = await client.post(
        base + "/importaciones/previsualizacion",
        files={
            "files": (
                "semana.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    borrador = respuesta.json()["revisiones"][0]["borrador"]
    async with sesiones() as db:
        assert await db.scalar(select(func.count()).select_from(ControlEvento)) == 0
    borrador["filas"][0]["kilometraje"] = "110000"
    assert (
        await client.post(base + "/importaciones/validaciones", json=borrador)
    ).status_code == 200
    confirmado = await client.post(base + "/importaciones", json=borrador)
    assert confirmado.status_code == 201, confirmado.text
    carga_id = confirmado.json()["carga_id"]
    assert (
        await client.get(base + f"/importaciones/{carga_id}/filas")
    ).status_code == 200
    assert (await client.delete(base + f"/importaciones/{carga_id}")).status_code == 422
    assert (
        await client.delete(base + f"/importaciones/{carga_id}?confirmar=true")
    ).status_code == 200
