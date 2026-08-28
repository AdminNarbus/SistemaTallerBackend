import pytest
from app.modules.neumaticos.services.formulario_neumatico_service import formulario_neumatico_service


@pytest.mark.asyncio
async def test_procesar_formulario_neumatico_sin_evidencia(db_session, seed_test_data):
    """Prueba el procesamiento de formulario de neumáticos sin archivo adjunto."""
    conductor_id = seed_test_data["conductor"].id

    res = await formulario_neumatico_service.procesar_formulario(
        usuario_id=conductor_id,
        maquina="BUS-505",
        tipo_bus="Doble Piso",
        ruedas='[{"posicion": "Delantera Izquierda", "profundidad_mm": 12.5}]',
        motivo="Cambio por desgaste",
        precio="150000",
        marca_fuego="MF-999888",
        evidencia=None,
        db=db_session,
    )

    assert res["status"] == "success"
    assert res["reporte_id"] is not None
    assert res["datos_recibidos"]["maquina"] == "BUS-505"
    assert res["datos_recibidos"]["marca_fuego"] == "MF-999888"
    assert res["datos_recibidos"]["evidencia_url"] is None


@pytest.mark.asyncio
async def test_procesar_formulario_neumatico_marca_fuego_opcional(db_session, seed_test_data):
    """Prueba que marca_fuego sea verdaderamente opcional."""
    conductor_id = seed_test_data["conductor"].id

    res = await formulario_neumatico_service.procesar_formulario(
        usuario_id=conductor_id,
        maquina="BUS-606",
        tipo_bus="Interurbano",
        ruedas='[]',
        motivo="Revisión de rutina",
        precio="0",
        marca_fuego=None,
        evidencia=None,
        db=db_session,
    )

    assert res["status"] == "success"
    assert res["datos_recibidos"]["marca_fuego"] is None
