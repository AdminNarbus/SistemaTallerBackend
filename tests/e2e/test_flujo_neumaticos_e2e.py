import pytest
import io


@pytest.mark.asyncio
async def test_flujo_neumaticos_e2e(client, seed_test_data):
    """
    PRUEBA DE SISTEMA / END-TO-END (E2E):
    Subida de formulario de neumáticos con evidencia física y posterior consulta de estáticos.
    """
    user_id = seed_test_data["conductor"].id

    fake_file_content = b"Content of a test tire evidence image"
    fake_image = io.BytesIO(fake_file_content)
    files = {"evidencia": ("neumatico_doblado.png", fake_image, "image/png")}

    data = {
        "usuario_id": str(user_id),
        "maquina": "BUS-909",
        "tipo_bus": "MiniBus",
        "ruedas": '[{"posicion": "Delantera Derecha", "profundidad_mm": 8.5}]',
        "motivo": "Pinchazo en ruta",
        "precio": "85000",
        "marca_fuego": "MF-777",
    }

    # 1. Enviar formulario multipart
    res_post = await client.post("/api/v1/formularioNeumatico", data=data, files=files)
    assert res_post.status_code == 200
    res_json = res_post.json()
    assert res_json["status"] == "success"

    evidencia_url = res_json["datos_recibidos"]["evidencia_url"]
    assert evidencia_url is not None
    assert evidencia_url.startswith("/uploads/evidencias/")

    # 2. Consultar el archivo servido estáticamente
    res_file = await client.get(evidencia_url)
    assert res_file.status_code == 200
    assert res_file.content == fake_file_content
