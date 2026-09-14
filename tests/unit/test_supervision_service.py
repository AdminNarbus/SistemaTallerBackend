import pytest
from unittest.mock import AsyncMock, MagicMock
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
from app.modules.mantencion.dtos.mantencion_dto import AsignarFallasSupervisoraDTO, SolicitudDTO
from app.modules.supervision.services import supervision_service, SupervisionService
from app.modules.supervision.repository import supervision_repository, SupervisionRepository
from app.modules.supervision.constants import (
    TipoAlertaSupervision,
    SeveridadAlerta,
    BUS_SIN_NUMERO,
)
from app.modules.supervision.dtos import (
    AlertaSupervisionDTO,
    ResumenTallerDTO,
    MetricasEstadoDTO,
)
from app.modules.supervision.utils import (
    calcular_porcentaje_resolucion,
    formatear_mensaje_alerta_repuesto,
    formatear_mensaje_alerta_pauta,
    formatear_mensaje_alerta_bus_sin_mecanicos,
    construir_alerta_supervision,
)


@pytest.mark.asyncio
async def test_supervision_resumen_taller_kpis(db_session, seed_test_data):
    """Prueba el cálculo de resumen y KPIs generales del taller en SupervisionService."""
    conductor = seed_test_data["conductor"]

    # 1. Sembrar categoría y fallas
    cat = CategoriaFalla(id=99, nombre="Sistema Eléctrico", is_active=True)
    falla1 = FallaTaller(id=901, categoria_id=99, nombre="Alternador sin carga", is_active=True)
    falla2 = FallaTaller(id=902, categoria_id=99, nombre="Batería agotada", is_active=True)
    db_session.add_all([cat, falla1, falla2])

    # 2. Sembrar bus en taller
    bus = Bus(id=77, n_bus="777", patente="SUP777", marca="Scania", modelo="K400", is_active=True, en_taller=True)
    db_session.add(bus)

    # 3. Sembrar solicitud con detalles (1 resuelto, 1 pendiente)
    sol = TallerSolicitud(
        id=701,
        n_bus="777",
        bus_id=77,
        usuario_creador_id=conductor.id,
        estado="EN_REPARACION",
        descripcion_general="Falla eléctrica total",
    )
    db_session.add(sol)
    await db_session.flush()

    det1 = TallerSolicitudDetalle(
        id=801,
        solicitud_id=701,
        falla_id=901,
        descripcion_personalizada="Alternador quemado",
        resuelto=True,
    )
    det2 = TallerSolicitudDetalle(
        id=802,
        solicitud_id=701,
        falla_id=902,
        descripcion_personalizada="Cambio de baterías",
        resuelto=False,
    )
    db_session.add_all([det1, det2])
    await db_session.commit()

    # 4. Consultar resumen general
    resumen = await supervision_service.get_resumen_taller(db_session)

    assert resumen.total_fallas_registradas >= 2
    assert resumen.total_fallas_resueltas >= 1
    assert resumen.porcentaje_resolucion_fallas > 0.0
    assert resumen.metricas_estado.buses_fisicamente_en_taller >= 1
    assert "777" in resumen.buses_activos_taller


@pytest.mark.asyncio
async def test_supervision_alertas_operacionales(db_session, seed_test_data):
    """Prueba la generación de alertas operacionales de taller."""
    conductor = seed_test_data["conductor"]

    # 1. Sembrar ítem de pauta
    pauta_item = PautaTallerItem(id=88, categoria="Motor", item="Nivel de aceite", orden=1, is_active=True)
    db_session.add(pauta_item)

    # 2. Sembrar orden con falta de repuestos y pauta con defecto
    sol = TallerSolicitud(
        id=702,
        n_bus="888",
        usuario_creador_id=conductor.id,
        estado="EN_REPARACION",
        descripcion_general="Prueba de alertas",
    )
    db_session.add(sol)
    await db_session.flush()

    det = TallerSolicitudDetalle(
        id=803,
        solicitud_id=702,
        descripcion_personalizada="Filtro de combustible tapado",
        falta_repuesto=True,
        comentario_repuesto="Esperando repuesto desde Santiago",
        resuelto=False,
    )
    pauta_resp = TallerSolicitudPauta(
        solicitud_id=702,
        item_id=88,
        estado="DEFECTO",
        observacion="Aceite negro con virutas",
    )
    db_session.add_all([det, pauta_resp])
    await db_session.commit()

    # 3. Consultar centro de alertas
    alertas = await supervision_service.get_alertas_taller(db_session)
    tipos = [a.tipo for a in alertas]

    assert "REPUESTO_FALTANTE" in tipos
    assert "DEFECTO_PAUTA" in tipos

    alerta_rep = next(a for a in alertas if a.tipo == "REPUESTO_FALTANTE" and a.solicitud_id == 702)
    assert "Esperando repuesto" in alerta_rep.mensaje
    assert alerta_rep.severidad == "ALTA"


@pytest.mark.asyncio
async def test_supervision_repository_consultas_atomicas(db_session, seed_test_data):
    """Prueba las consultas SQL analíticas de persistencia pura en SupervisionRepository."""
    # 1. get_total_buses_en_taller
    total_buses = await supervision_repository.get_total_buses_en_taller(db_session)
    assert isinstance(total_buses, int)

    # 2. get_conteos_por_estado
    conteos = await supervision_repository.get_conteos_por_estado(db_session)
    assert isinstance(conteos, dict)

    # 3. get_conteos_fallas
    total_f, resueltas_f = await supervision_repository.get_conteos_fallas(db_session)
    assert isinstance(total_f, int)
    assert isinstance(resueltas_f, int)
    assert total_f >= resueltas_f

    # 4. get_buses_activos_taller
    activos = await supervision_repository.get_buses_activos_taller(db_session)
    assert isinstance(activos, list)


# ==============================================================================
# PRUEBAS UNITARIAS PURAS DE UTILS (FUNCIONES DETERMINISTAS Y MATEMÁTICAS)
# ==============================================================================


def test_calcular_porcentaje_resolucion_normal():
    """Valida el cálculo correcto con redondeo a dos decimales."""
    # Arrange
    total = 10
    resueltas = 5
    # Act
    resultado = calcular_porcentaje_resolucion(total, resueltas)
    # Assert
    assert resultado == 50.0

    # Act 2 (con decimales)
    resultado_decimal = calcular_porcentaje_resolucion(3, 1)
    # Assert 2
    assert resultado_decimal == 33.33


def test_calcular_porcentaje_resolucion_cero_o_negativos():
    """Valida la protección contra división por cero y valores atípicos."""
    # Arrange & Act & Assert
    assert calcular_porcentaje_resolucion(0, 0) == 0.0
    assert calcular_porcentaje_resolucion(0, 5) == 0.0
    assert calcular_porcentaje_resolucion(10, 0) == 0.0
    assert calcular_porcentaje_resolucion(-5, 2) == 0.0
    assert calcular_porcentaje_resolucion(10, -2) == 0.0


def test_calcular_porcentaje_resolucion_completa():
    """Valida el 100% de resolución exacta."""
    # Arrange & Act & Assert
    assert calcular_porcentaje_resolucion(8, 8) == 100.0


def test_formatear_mensajes_alertas():
    """Valida la construcción semántica de los mensajes de alertas operacionales."""
    # 1. Repuesto con comentario
    msg1 = formatear_mensaje_alerta_repuesto(12, "105", "Esperando alternador")
    assert msg1 == "Falla #12 en Bus 105 detenida por falta de repuestos: Esperando alternador"

    # 2. Repuesto sin comentario
    msg2 = formatear_mensaje_alerta_repuesto(12, "105", None)
    assert msg2 == "Falla #12 en Bus 105 detenida por falta de repuestos"

    # 3. Repuesto con bus vacío (usa fallback BUS_SIN_NUMERO)
    msg3 = formatear_mensaje_alerta_repuesto(12, "", "")
    assert msg3 == f"Falla #12 en Bus {BUS_SIN_NUMERO} detenida por falta de repuestos"

    # 4. Pauta preventiva con ítem nombrado
    msg4 = formatear_mensaje_alerta_pauta("202", item_nombre="Presión de frenos", item_id=3)
    assert msg4 == "Ítem de pauta preventiva con defecto en Bus 202: Presión de frenos"

    # 5. Pauta preventiva sin nombre de ítem (usa ID)
    msg5 = formatear_mensaje_alerta_pauta("202", item_nombre=None, item_id=7)
    assert msg5 == "Ítem de pauta preventiva con defecto en Bus 202: Ítem #7"

    # 6. Bus sin mecánicos
    msg6 = formatear_mensaje_alerta_bus_sin_mecanicos("303")
    assert msg6 == "Bus 303 figura EN_REPARACION pero no tiene mecánicos activos asignados"


def test_construir_alerta_supervision():
    """Valida la instanciación de AlertaSupervisionDTO mediante el helper puro."""
    # Arrange & Act
    alerta = construir_alerta_supervision(
        tipo=TipoAlertaSupervision.REPUESTO_FALTANTE,
        severidad=SeveridadAlerta.ALTA,
        solicitud_id=501,
        n_bus="404",
        mensaje="Alerta de prueba",
        detalle_id=99,
    )

    # Assert
    assert isinstance(alerta, AlertaSupervisionDTO)
    assert alerta.tipo == TipoAlertaSupervision.REPUESTO_FALTANTE
    assert alerta.severidad == SeveridadAlerta.ALTA
    assert alerta.solicitud_id == 501
    assert alerta.n_bus == "404"
    assert alerta.detalle_id == 99
    assert alerta.mensaje == "Alerta de prueba"


# ==============================================================================
# PRUEBAS UNITARIAS AISLADAS DE SUPERVISION SERVICE (PATRÓN AAA CON MOCKS)
# ==============================================================================


def test_supervision_service_init_custom_dependencies():
    """Verifica la inyección de dependencias en el constructor de SupervisionService."""
    # Arrange
    mock_repo = MagicMock(spec=SupervisionRepository)
    mock_mantencion = MagicMock()

    # Act
    service = SupervisionService(repository=mock_repo, mantencion_srv=mock_mantencion)

    # Assert
    assert service.repo is mock_repo
    assert service.mantencion is mock_mantencion


@pytest.mark.asyncio
async def test_supervision_service_get_auditoria_aislado():
    """Verifica que get_auditoria_solicitudes delegue al repo y mapee DTOs correctamente."""
    # Arrange
    mock_repo = AsyncMock(spec=SupervisionRepository)
    mock_mantencion = MagicMock()
    mock_db = AsyncMock()

    raw_item = {"id": 100, "n_bus": "500", "estado": "EN_REPARACION"}
    mock_repo.get_auditoria.return_value = [raw_item]

    dummy_dto = MagicMock(spec=SolicitudDTO)
    dummy_dto.id = 100
    dummy_dto.n_bus = "500"
    mock_mantencion.mapear_a_solicitud_dto.return_value = dummy_dto

    service = SupervisionService(repository=mock_repo, mantencion_srv=mock_mantencion)

    # Act
    resultado = await service.get_auditoria_solicitudes(
        db=mock_db,
        n_bus="500",
        estado="EN_REPARACION",
        mecanico_nombre="Juan",
        skip=0,
        limit=10,
    )

    # Assert
    assert len(resultado) == 1
    assert resultado[0].id == 100
    mock_repo.get_auditoria.assert_awaited_once_with(
        mock_db,
        n_bus="500",
        estado="EN_REPARACION",
        mecanico_nombre="Juan",
        skip=0,
        limit=10,
    )
    mock_mantencion.mapear_a_solicitud_dto.assert_called_once_with(raw_item)


@pytest.mark.asyncio
async def test_supervision_service_get_resumen_aislado():
    """Verifica que get_resumen_taller delegue directamente a get_resumen_taller_consolidado."""
    # Arrange
    mock_repo = AsyncMock(spec=SupervisionRepository)
    mock_db = AsyncMock()
    dummy_resumen = MagicMock(spec=ResumenTallerDTO)
    mock_repo.get_resumen_taller_consolidado.return_value = dummy_resumen

    service = SupervisionService(repository=mock_repo)

    # Act
    resultado = await service.get_resumen_taller(mock_db)

    # Assert
    assert resultado is dummy_resumen
    mock_repo.get_resumen_taller_consolidado.assert_awaited_once_with(mock_db)


@pytest.mark.asyncio
async def test_supervision_service_get_alertas_aislado():
    """Verifica que get_alertas_taller delegue directamente a get_alertas_activas."""
    # Arrange
    mock_repo = AsyncMock(spec=SupervisionRepository)
    mock_db = AsyncMock()
    dummy_alertas = [MagicMock(spec=AlertaSupervisionDTO)]
    mock_repo.get_alertas_activas.return_value = dummy_alertas

    service = SupervisionService(repository=mock_repo)

    # Act
    resultado = await service.get_alertas_taller(mock_db)

    # Assert
    assert resultado is dummy_alertas
    mock_repo.get_alertas_activas.assert_awaited_once_with(mock_db)


@pytest.mark.asyncio
async def test_supervision_service_asignar_fallas_aislado():
    """Verifica que asignar_fallas_supervisora coordine con mantencion_service."""
    # Arrange
    mock_mantencion = AsyncMock()
    mock_db = AsyncMock()
    dto = AsignarFallasSupervisoraDTO(mecanico_id=42, detalles_ids=[1, 2])
    dummy_solicitud = MagicMock(spec=SolicitudDTO)
    dummy_solicitud.id = 888
    mock_mantencion.asignar_fallas_supervisora.return_value = dummy_solicitud

    service = SupervisionService(mantencion_srv=mock_mantencion)

    # Act
    resultado = await service.asignar_fallas_supervisora(
        db=mock_db,
        solicitud_id=888,
        dto=dto,
        supervisor_id=10,
    )

    # Assert
    assert resultado is dummy_solicitud
    mock_mantencion.asignar_fallas_supervisora.assert_awaited_once_with(
        mock_db,
        solicitud_id=888,
        dto=dto,
        supervisor_id=10,
    )
