import pytest
import io


@pytest.mark.asyncio
async def test_get_formulario_neumatico(client):
    """Prueba GET /api/v1/formularioNeumatico."""
    res = await client.get("/api/v1/formularioNeumatico")
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["status"] == "success"


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
