import io
import pytest


@pytest.mark.asyncio
async def test_get_formulario_neumatico(client):
    """Prueba GET /api/v1/formularios/neumaticos/estado."""
    res = await client.get("/api/v1/formularios/neumaticos/estado")
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["status"] == "success"
    assert "activo y disponible" in json_data["message"] or "correctamente" in json_data["message"]


@pytest.mark.asyncio
async def test_post_formulario_neumatico_with_file_upload(client, seed_test_data):
    """Prueba POST /api/v1/formularios/neumaticos con carga multipart/form-data y evidencia."""
    user_id = seed_test_data["conductor"].id

    # Simulación de un archivo de imagen en memoria
    fake_image = io.BytesIO(b"fake image bytes content for test")
    files = {"evidencia": ("evidencia_test.jpg", fake_image, "image/jpeg")}

    data = {
        "usuario_id": str(user_id),
        "maquina": "BUS-707",
        "ruedas": '[{"posicion": "Eje Trasero Izquierdo", "profundidad_mm": 14.0}]',
        "motivo": "Inspección periódica",
        "marca_fuego": "MF-123456",
    }

    res = await client.post("/api/v1/formularios/neumaticos", data=data, files=files)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "success"
    assert res_data["reporte_id"] is not None
    assert "/uploads/evidencias/" in res_data["datos_recibidos"]["evidencia_url"]
    assert "precio" not in res_data["datos_recibidos"]


@pytest.mark.asyncio
async def test_post_formulario_neumatico_con_jwt_autenticado(client, seed_test_data, auth_headers_conductor):
    """Prueba POST /api/v1/formularios/neumaticos extrayendo el usuario del token JWT."""
    conductor = seed_test_data["conductor"]

    data = {
        "maquina": "BUS-999",
        "ruedas": "[1]",
        "motivo": "Cambio de neumático vía JWT",
    }

    res = await client.post("/api/v1/formularios/neumaticos", data=data, headers=auth_headers_conductor)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "success"
    assert res_data["reporte_id"] is not None
    assert res_data["datos_recibidos"]["usuario_id"] == conductor.id
    assert "precio" not in res_data["datos_recibidos"]

    # Consultar el reporte por ID a través del router
    reporte_id = res_data["reporte_id"]
    res_get = await client.get(f"/api/v1/formularios/neumaticos/reportes/{reporte_id}", headers=auth_headers_conductor)
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["id"] == reporte_id
    assert data_get["usuario_id"] == conductor.id
    assert data_get["n_bus"] == "BUS-999"


@pytest.mark.asyncio
async def test_get_reportes_paginados_api(client, seed_test_data, auth_headers_conductor):
    """Prueba GET /api/v1/formularios/neumaticos/reportes con paginación, filtros y cabecera X-Total-Count."""
    # 1. Crear un reporte previo
    data = {
        "maquina": "BUS-LIST-API",
        "ruedas": "[1]",
        "motivo": "Test paginación API",
    }
    await client.post("/api/v1/formularios/neumaticos", data=data, headers=auth_headers_conductor)

    # 2. Consultar listado paginado
    res = await client.get("/api/v1/formularios/neumaticos/reportes?page=1&page_size=10", headers=auth_headers_conductor)
    assert res.status_code == 200
    json_data = res.json()
    assert "items" in json_data
    assert "total" in json_data
    assert json_data["page"] == 1
    assert json_data["page_size"] == 10
    assert "X-Total-Count" in res.headers
    assert int(res.headers["X-Total-Count"]) == json_data["total"]

    # 3. Filtrar por máquina específica
    res_filtrado = await client.get(
        "/api/v1/formularios/neumaticos/reportes?n_bus=BUS-LIST-API", headers=auth_headers_conductor
    )
    assert res_filtrado.status_code == 200
    data_filtrada = res_filtrado.json()
    assert data_filtrada["total"] >= 1
    assert all(r["n_bus"] == "BUS-LIST-API" for r in data_filtrada["items"])


