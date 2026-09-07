import io
import pytest


@pytest.mark.asyncio
async def test_get_formulario_neumatico(client):
    """Prueba GET /api/v1/formularioNeumatico."""
    res = await client.get("/api/v1/formularioNeumatico")
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["status"] == "success"
    assert json_data["message"] == "Solicitud de formularioNeumatico recibida correctamente"


@pytest.mark.asyncio
async def test_post_formulario_neumatico_with_file_upload(client, seed_test_data):
    """Prueba POST /api/v1/formularioNeumatico con carga multipart/form-data y evidencia."""
    user_id = seed_test_data["conductor"].id

    # Simulación de un archivo de imagen en memoria
    fake_image = io.BytesIO(b"fake image bytes content for test")
    files = {"evidencia": ("evidencia_test.jpg", fake_image, "image/jpeg")}

    data = {
        "usuario_id": str(user_id),
        "maquina": "BUS-707",
        "tipo_bus": "Interurbano",
        "ruedas": '[{"posicion": "Eje Trasero Izquierdo", "profundidad_mm": 14.0}]',
        "motivo": "Inspección periódica",
        "precio": "120000",
        "marca_fuego": "MF-123456",
    }

    res = await client.post("/api/v1/formularioNeumatico", data=data, files=files)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "success"
    assert res_data["reporte_id"] is not None
    assert "/uploads/evidencias/" in res_data["datos_recibidos"]["evidencia_url"]


@pytest.mark.asyncio
async def test_post_formulario_neumatico_con_jwt_autenticado(client, seed_test_data, auth_headers_conductor):
    """Prueba POST /api/v1/formularioNeumatico extrayendo el usuario del token JWT."""
    conductor = seed_test_data["conductor"]

    data = {
        "maquina": "BUS-999",
        "tipo_bus": "Doble Piso",
        "motivo": "Cambio de neumático vía JWT",
        "precio": "250000",
    }

    res = await client.post("/api/v1/formularioNeumatico", data=data, headers=auth_headers_conductor)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "success"
    assert res_data["reporte_id"] is not None
    assert res_data["datos_recibidos"]["usuario_id"] == conductor.id

    # Consultar el reporte por ID a través del router
    reporte_id = res_data["reporte_id"]
    res_get = await client.get(f"/api/v1/reportes/{reporte_id}", headers=auth_headers_conductor)
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["id"] == reporte_id
    assert data_get["usuario_id"] == conductor.id
    assert data_get["n_bus"] == "BUS-999"
