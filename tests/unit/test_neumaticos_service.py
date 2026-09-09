import io
import pytest
from datetime import datetime, timezone
from starlette.datastructures import UploadFile as StarletteUploadFile
from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.neumaticos.dtos.reporte_neumatico_dto import ReporteNeumaticoCreateDTO
from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico
from app.modules.neumaticos.repository.neumatico_repository import neumatico_repository
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


@pytest.mark.asyncio
async def test_procesar_formulario_con_dto(db_session, seed_test_data):
    """Prueba el servicio procesando directamente un ReporteNeumaticoCreateDTO."""
    conductor_id = seed_test_data["conductor"].id
    dto = ReporteNeumaticoCreateDTO(
        usuario_id=conductor_id,
        maquina="BUS-707",
        tipo_bus="Clásico",
        ruedas=[{"posicion": "Trasera Derecha", "profundidad_mm": 10.0}],
        motivo="Desgaste parejo",
        precio="200.000",
        marca_fuego="MF-111222",
    )

    res = await formulario_neumatico_service.procesar_formulario(
        dto=dto,
        db=db_session,
        usuario_id=conductor_id,
    )

    assert res.status == "success"
    assert res.reporte_id is not None
    assert res.datos_recibidos["maquina"] == "BUS-707"
    assert res["reporte_id"] == res.reporte_id


@pytest.mark.asyncio
async def test_obtener_estado_formulario():
    """Prueba la obtención de disponibilidad del formulario."""
    status_dto = await formulario_neumatico_service.obtener_estado_formulario()
    assert status_dto.status == "success"
    assert status_dto["status"] == "success"


@pytest.mark.asyncio
async def test_get_reporte_by_id_flujo_completo(db_session, seed_test_data):
    """Prueba consultar un reporte existente y validar NotFoundException."""
    conductor_id = seed_test_data["conductor"].id
    dto = ReporteNeumaticoCreateDTO(
        usuario_id=conductor_id,
        maquina="BUS-808",
        tipo_bus="Premium",
        motivo="Test consulta ID",
    )
    res_creacion = await formulario_neumatico_service.procesar_formulario(
        dto=dto, db=db_session, usuario_id=conductor_id
    )

    # 1. Consulta exitosa
    reporte_dto = await formulario_neumatico_service.get_reporte_by_id(
        db=db_session, reporte_id=res_creacion.reporte_id
    )
    assert reporte_dto.id == res_creacion.reporte_id
    assert reporte_dto.n_bus == "BUS-808"

    # 2. Consulta de ID inexistente debe lanzar NotFoundException
    with pytest.raises(NotFoundException):
        await formulario_neumatico_service.get_reporte_by_id(db=db_session, reporte_id=999999)


@pytest.mark.asyncio
async def test_neumatico_repository_operaciones_atomicas(db_session, seed_test_data):
    """Prueba operaciones CRUD atómicas del repositorio (persistencia pura)."""
    conductor_id = seed_test_data["conductor"].id
    bus_existente = seed_test_data.get("bus")

    # 1. add()
    nuevo_reporte = ReporteNeumatico(
        usuario_id=conductor_id,
        n_bus=bus_existente.n_bus if bus_existente else "BUS-ATOM-1",
        bus_id=bus_existente.id if bus_existente else None,
        tipo_bus="Test Atómico",
        motivo="Verificación repository",
        fecha_subida=datetime.now(timezone.utc),
    )
    saved = await neumatico_repository.add(db_session, nuevo_reporte)
    assert saved.id is not None

    # 2. get_by_id()
    fetched = await neumatico_repository.get_by_id(db_session, saved.id)
    assert fetched is not None
    assert fetched.id == saved.id

    # 3. get_bus_by_numero()
    if bus_existente:
        bus_found = await neumatico_repository.get_bus_by_numero(db_session, bus_existente.n_bus)
        assert bus_found is not None
        assert bus_found.id == bus_existente.id

    # 4. list_reportes() y count()
    total = await neumatico_repository.count(db_session)
    assert total >= 1
    lista = await neumatico_repository.list_reportes(db_session, limit=10)
    assert len(lista) >= 1


@pytest.mark.asyncio
async def test_procesar_formulario_evidencia_extension_invalida(db_session, seed_test_data):
    """Prueba que subir un archivo con extensión no permitida lance BusinessRuleException."""
    conductor_id = seed_test_data["conductor"].id
    fake_file = io.BytesIO(b"binary executable")
    upload_file = StarletteUploadFile(filename="script.exe", file=fake_file)

    with pytest.raises(BusinessRuleException) as exc_info:
        await formulario_neumatico_service.procesar_formulario(
            usuario_id=conductor_id,
            maquina="BUS-101",
            evidencia=upload_file,
            db=db_session,
        )
    assert "Tipo de archivo no permitido" in str(exc_info.value)


@pytest.mark.asyncio
async def test_procesar_formulario_evidencia_tamano_excedido(db_session, seed_test_data):
    """Prueba que un archivo que excede 10 MB lance BusinessRuleException."""
    conductor_id = seed_test_data["conductor"].id
    # Simular 11 MB de contenido
    large_content = b"x" * (11 * 1024 * 1024)
    fake_file = io.BytesIO(large_content)
    upload_file = StarletteUploadFile(filename="foto_pesada.jpg", file=fake_file)

    with pytest.raises(BusinessRuleException) as exc_info:
        await formulario_neumatico_service.procesar_formulario(
            usuario_id=conductor_id,
            maquina="BUS-101",
            evidencia=upload_file,
            db=db_session,
        )
    assert "supera el tamaño máximo" in str(exc_info.value)

