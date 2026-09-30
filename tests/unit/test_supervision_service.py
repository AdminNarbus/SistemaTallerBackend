import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from app.modules.buses.models.bus import Bus
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.falla_taller import FallaTaller
from app.modules.taller.models.categoria_falla import CategoriaFalla
from app.modules.taller.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
from app.modules.taller.dtos import (
    AsignarFallasSupervisoraDTO,
    CambiarEstadoSolicitudDTO,
    SolicitudDTO,
    SolicitudResumenDTO,
)
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
    formatear_mensaje_ot_sin_ingreso_taller,
    formatear_mensaje_tiempo_taller_excedido,
    formatear_mensaje_liberado_tiempo_excedido,
    construir_alerta_supervision,
    formatear_comentario_cambio_estado,
    calcular_severidad_tiempo_permanencia,
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
    """Prueba la generación de alertas operacionales de taller (OT_SIN_INGRESO_TALLER y LIBERADO_TIEMPO_EXCEDIDO)."""
    from datetime import datetime, timedelta, timezone
    conductor = seed_test_data["conductor"]

    # 1. Sembrar bus en flota
    bus = Bus(id=770, n_bus="888", patente="SUP888", marca="Scania", modelo="K400", is_active=True, en_taller=False)
    db_session.add(bus)
    await db_session.flush()

    # 2. Sembrar orden con fecha_creacion antigua sin haber ingresado a taller (fecha_primer_ingreso_taller IS NULL: 72 horas)
    fecha_antigua = datetime.now(timezone.utc) - timedelta(hours=72)
    sol1 = TallerSolicitud(
        id=702,
        n_bus="888",
        bus_id=770,
        usuario_creador_id=conductor.id,
        estado="PENDIENTE",
        descripcion_general="Prueba de alertas OT sin ingreso a taller",
        fecha_creacion=fecha_antigua,
        fecha_primer_ingreso_taller=None,
    )
    # Sembrar orden en estado LIBERADO con fecha_liberacion antigua (excediendo umbral: 96 horas)
    fecha_lib_antigua = datetime.now(timezone.utc) - timedelta(hours=96)
    sol2 = TallerSolicitud(
        id=703,
        n_bus="889",
        usuario_creador_id=conductor.id,
        estado="LIBERADO",
        descripcion_general="Prueba de alertas liberado",
        fecha_creacion=fecha_lib_antigua,
        fecha_liberacion=fecha_lib_antigua,
    )
    db_session.add_all([sol1, sol2])
    await db_session.commit()

    # 3. Consultar centro de alertas
    alertas = await supervision_service.get_alertas_taller(db_session)
    tipos = [a.tipo for a in alertas]

    assert TipoAlertaSupervision.OT_SIN_INGRESO_TALLER in tipos
    assert TipoAlertaSupervision.LIBERADO_TIEMPO_EXCEDIDO in tipos

    alerta_sin_ingreso = next(a for a in alertas if a.tipo == TipoAlertaSupervision.OT_SIN_INGRESO_TALLER and a.solicitud_id == 702)
    assert "888" in alerta_sin_ingreso.mensaje
    assert "sin haber ingresado a taller" in alerta_sin_ingreso.mensaje
    assert alerta_sin_ingreso.horas_acumuladas is not None
    assert alerta_sin_ingreso.horas_acumuladas >= 71.0

    alerta_lib = next(a for a in alertas if a.tipo == TipoAlertaSupervision.LIBERADO_TIEMPO_EXCEDIDO and a.solicitud_id == 703)
    assert "889" in alerta_lib.mensaje
    assert alerta_lib.horas_acumuladas is not None
    assert alerta_lib.horas_acumuladas >= 95.0


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
    total_f, resueltas_f, bloq_f = await supervision_repository.get_conteos_fallas(db_session)
    assert isinstance(total_f, int)
    assert isinstance(resueltas_f, int)
    assert isinstance(bloq_f, int)
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
    # 1. OT sin ingreso a taller con horas < 48
    msg1 = formatear_mensaje_ot_sin_ingreso_taller("101", 36.0, "PENDIENTE")
    assert msg1 == "Bus 101 tiene OT activa hace 36 horas sin haber ingresado a taller"

    # 2. OT sin ingreso a taller con días >= 48
    msg2 = formatear_mensaje_ot_sin_ingreso_taller("102", 72.0, "PENDIENTE")
    assert msg2 == "Bus 102 tiene OT activa hace 3.0 días sin haber ingresado a taller"

    # 3. OT sin ingreso a taller sin n_bus (usa fallback)
    msg3 = formatear_mensaje_ot_sin_ingreso_taller("", 50.0)
    assert msg3 == f"Bus {BUS_SIN_NUMERO} tiene OT activa hace 2.1 días sin haber ingresado a taller"

    # 4. Liberado tiempo excedido
    msg4 = formatear_mensaje_liberado_tiempo_excedido("103", 96.0)
    assert msg4 == "Bus 103 lleva 4.0 días circulando en estado LIBERADO con fallas pendientes"

    # 5. Liberado tiempo excedido < 48 horas
    msg5 = formatear_mensaje_liberado_tiempo_excedido("104", 30.0)
    assert msg5 == "Bus 104 lleva 30 horas circulando en estado LIBERADO con fallas pendientes"


def test_construir_alerta_supervision():
    """Valida la instanciación de AlertaSupervisionDTO mediante el helper puro."""
    # Arrange & Act
    alerta = construir_alerta_supervision(
        tipo=TipoAlertaSupervision.OT_SIN_INGRESO_TALLER,
        severidad=SeveridadAlerta.ALTA,
        solicitud_id=501,
        n_bus="404",
        mensaje="Alerta de prueba",
        horas_acumuladas=220.5,
    )

    # Assert
    assert isinstance(alerta, AlertaSupervisionDTO)
    assert alerta.tipo == TipoAlertaSupervision.OT_SIN_INGRESO_TALLER
    assert alerta.severidad == SeveridadAlerta.ALTA
    assert alerta.solicitud_id == 501
    assert alerta.n_bus == "404"
    assert alerta.detalle_id is None
    assert alerta.horas_acumuladas == 220.5
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
    """Verifica que get_auditoria_solicitudes delegue al repo y mapee SolicitudResumenDTO correctamente."""
    # Arrange
    mock_repo = AsyncMock(spec=SupervisionRepository)
    mock_mantencion = MagicMock()
    mock_db = AsyncMock()

    raw_item = {
        "id": 100,
        "n_bus": "500",
        "estado": "EN_REPARACION",
        "fecha_creacion": datetime(2026, 9, 21, 12, 0, 0),
        "usuario_creador_nombre": "Carlos Conductor",
        "horas_en_taller": 4.5,
        "total_fallas": 2,
        "fallas_pendientes": 1,
        "mecanicos": [{"mecanico_nombre": "Juan Pérez", "is_activo": True}],
    }
    mock_repo.get_auditoria.return_value = [raw_item]

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
    assert isinstance(resultado[0], SolicitudResumenDTO)
    assert resultado[0].id == 100
    assert resultado[0].n_bus == "500"
    assert resultado[0].estado == "EN_REPARACION"
    assert resultado[0].chofer == "Carlos Conductor"
    assert resultado[0].tiempo_taller == 4.5
    assert resultado[0].numero_fallas == 1
    mock_repo.get_auditoria.assert_awaited_once_with(
        mock_db,
        n_bus="500",
        estado="EN_REPARACION",
        mecanico_nombre="Juan",
        skip=0,
        limit=10,
    )


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
    """Verifica que asignar_fallas_supervisora coordine con taller_service."""
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


def test_supervision_utils_formatear_comentario_cambio_estado():
    """Valida la función pura de formateo de comentarios de bitácora para cambio de estado."""
    # Con motivo
    texto_con_motivo = formatear_comentario_cambio_estado(
        supervisor_nombre="Laura Rojas",
        estado_anterior="REPORTADO",
        nuevo_estado="EN_REPARACION",
        motivo="Ingreso urgente a fosa 2",
    )
    assert texto_con_motivo == "Supervisora Laura Rojas cambió el estado de REPORTADO a EN_REPARACION. Motivo: Ingreso urgente a fosa 2"

    # Sin motivo
    texto_sin_motivo = formatear_comentario_cambio_estado(
        supervisor_nombre="Laura Rojas",
        estado_anterior="EN_REPARACION",
        nuevo_estado="PENDIENTE",
        motivo=None,
    )
    assert texto_sin_motivo == "Supervisora Laura Rojas cambió el estado de EN_REPARACION a PENDIENTE."


@pytest.mark.asyncio
async def test_supervision_service_cambiar_estado_aislado():
    """Verifica que cambiar_estado_solicitud coordine con taller_service aplicando DIP."""
    mock_mantencion = AsyncMock()
    mock_db = AsyncMock()
    dto = CambiarEstadoSolicitudDTO(estado="PENDIENTE", comentario="Pausa operacional")
    dummy_solicitud = MagicMock(spec=SolicitudDTO)
    dummy_solicitud.id = 555
    mock_mantencion.cambiar_estado_solicitud.return_value = dummy_solicitud

    service = SupervisionService(mantencion_srv=mock_mantencion)

    resultado = await service.cambiar_estado_solicitud(
        db=mock_db,
        solicitud_id=555,
        dto=dto,
        supervisor_id=1,
        supervisor_nombre="Jefa Taller",
    )

    assert resultado is dummy_solicitud
    mock_mantencion.cambiar_estado_solicitud.assert_awaited_once_with(
        mock_db,
        solicitud_id=555,
        dto=dto,
        supervisor_id=1,
        supervisor_nombre="Jefa Taller",
    )


@pytest.mark.asyncio
async def test_cambiar_estado_solicitud_flujo_completo(db_session, seed_test_data):
    """Verifica el ciclo de vida de cambio de estado en BD: REPORTADO -> FINALIZADO -> EN_REPARACION."""
    conductor = seed_test_data["conductor"]
    supervisor = seed_test_data["supervisor"]

    bus = Bus(id=81, n_bus="881", patente="SUP881", marca="Scania", is_active=True, en_taller=True)
    db_session.add(bus)
    await db_session.flush()

    sol = TallerSolicitud(
        id=781,
        n_bus="881",
        bus_id=81,
        usuario_creador_id=conductor.id,
        estado="REPORTADO",
        descripcion_general="Prueba cambio de estado",
    )
    db_session.add(sol)
    await db_session.commit()

    # 1. Cambiar de REPORTADO a FINALIZADO
    dto_finalizar = CambiarEstadoSolicitudDTO(
        estado="FINALIZADO",
        comentario="Cierre directo por supervisión",
        liberar_bus_taller=True,
    )
    res_fin = await supervision_service.cambiar_estado_solicitud(
        db_session,
        solicitud_id=781,
        dto=dto_finalizar,
        supervisor_id=supervisor.id,
        supervisor_nombre=supervisor.nombre_completo,
    )
    assert res_fin.estado == "FINALIZADO"
    assert res_fin.fecha_cierre is not None
    assert bus.en_taller is False
    assert any(c.tipo == "CAMBIO_ESTADO" for c in res_fin.comentarios)

    # 2. Reabrir desde FINALIZADO a EN_REPARACION
    dto_reabrir = CambiarEstadoSolicitudDTO(
        estado="EN_REPARACION",
        comentario="Reapertura: falla persiste",
    )
    res_reabierta = await supervision_service.cambiar_estado_solicitud(
        db_session,
        solicitud_id=781,
        dto=dto_reabrir,
        supervisor_id=supervisor.id,
        supervisor_nombre=supervisor.nombre_completo,
    )
    assert res_reabierta.estado == "EN_REPARACION"
    assert res_reabierta.fecha_cierre is None
    assert bus.en_taller is True


@pytest.mark.asyncio
async def test_get_mecanicos_con_carga_unit(db_session, seed_test_data):
    """Verifica la consulta de carga de mecánicos activos y disponibilidad."""
    mecanicos_carga = await supervision_service.get_mecanicos_con_carga(db_session)
    assert isinstance(mecanicos_carga, list)
    assert len(mecanicos_carga) >= 1
    m1 = mecanicos_carga[0]
    assert hasattr(m1, "id")
    assert hasattr(m1, "nombre_completo")
    assert hasattr(m1, "username")
    assert hasattr(m1, "fallas_activas_count")
    assert hasattr(m1, "disponible")
    assert isinstance(m1.disponible, bool)


@pytest.mark.asyncio
async def test_alertas_formateo_tiempo_mensajes():
    """Verifica los formateadores de mensajes para alertas operacionales."""
    msg_taller_horas = formatear_mensaje_ot_sin_ingreso_taller("101", 36.0, "PENDIENTE")
    assert "tiene OT activa hace 36 horas sin haber ingresado a taller" in msg_taller_horas

    msg_taller_dias = formatear_mensaje_ot_sin_ingreso_taller("102", 72.0, "PENDIENTE")
    assert "tiene OT activa hace 3.0 días sin haber ingresado a taller" in msg_taller_dias

    msg_liberado_dias = formatear_mensaje_liberado_tiempo_excedido("103", 96.0)
    assert "4.0 días circulando en estado LIBERADO con fallas pendientes" in msg_liberado_dias


@pytest.mark.asyncio
async def test_ciclo_fecha_liberacion_en_cambio_estado(db_session, seed_test_data):
    """Verifica que al transicionar a LIBERADO se asigne fecha_liberacion y se limpie al volver a EN_REPARACION."""
    conductor = seed_test_data["conductor"]
    supervisor = seed_test_data["supervisor"]

    bus = Bus(id=82, n_bus="882", patente="SUP882", marca="Scania", is_active=True, en_taller=True)
    db_session.add(bus)
    await db_session.flush()

    sol = TallerSolicitud(
        id=782,
        n_bus="882",
        bus_id=82,
        usuario_creador_id=conductor.id,
        estado="EN_REPARACION",
        descripcion_general="Prueba ciclo fecha_liberacion",
    )
    db_session.add(sol)
    await db_session.commit()

    # 1. Pasar a LIBERADO
    dto_lib = CambiarEstadoSolicitudDTO(
        estado="LIBERADO",
        comentario="Egreso temporal con averías menores",
        liberar_bus_taller=True,
    )
    res_lib = await supervision_service.cambiar_estado_solicitud(
        db_session,
        solicitud_id=782,
        dto=dto_lib,
        supervisor_id=supervisor.id,
        supervisor_nombre=supervisor.nombre_completo,
    )
    assert res_lib.estado == "LIBERADO"
    assert res_lib.fecha_liberacion is not None
    assert bus.en_taller is False

    # 2. Retomar a EN_REPARACION
    dto_retomar = CambiarEstadoSolicitudDTO(
        estado="EN_REPARACION",
        comentario="Reingreso a maestranza para concluir reparación",
    )
    res_retomar = await supervision_service.cambiar_estado_solicitud(
        db_session,
        solicitud_id=782,
        dto=dto_retomar,
        supervisor_id=supervisor.id,
        supervisor_nombre=supervisor.nombre_completo,
    )
    assert res_retomar.estado == "EN_REPARACION"
    assert res_retomar.fecha_liberacion is None
    assert bus.en_taller is True


def test_alertas_escalonamiento_4_niveles_severidad():
    """
    Verifica el cálculo y escalonamiento de severidad de permanencia en 4 niveles canónicos:
    - BAJA: 2 a 4 días (48h a 119h)
    - MEDIA: 5 a 8 días (120h a 215h)
    - ALTA: 9 a 12 días (216h a 311h)
    - CRITICA: 13+ días (>= 312h)
    """
    # 1. Arrange & Act - Taller
    sev_taller_baja = calcular_severidad_tiempo_permanencia(horas=72.0, es_liberado=False)     # 3 días
    sev_taller_media = calcular_severidad_tiempo_permanencia(horas=144.0, es_liberado=False)   # 6 días
    sev_taller_alta = calcular_severidad_tiempo_permanencia(horas=240.0, es_liberado=False)    # 10 días
    sev_taller_critica = calcular_severidad_tiempo_permanencia(horas=336.0, es_liberado=False) # 14 días

    # Assert - Taller
    assert sev_taller_baja == SeveridadAlerta.BAJA
    assert sev_taller_media == SeveridadAlerta.MEDIA
    assert sev_taller_alta == SeveridadAlerta.ALTA
    assert sev_taller_critica == SeveridadAlerta.CRITICA

    # 2. Arrange & Act - Liberado
    sev_lib_baja = calcular_severidad_tiempo_permanencia(horas=48.0, es_liberado=True)      # 2 días
    sev_lib_media = calcular_severidad_tiempo_permanencia(horas=120.0, es_liberado=True)    # 5 días
    sev_lib_alta = calcular_severidad_tiempo_permanencia(horas=216.0, es_liberado=True)     # 9 días
    sev_lib_critica = calcular_severidad_tiempo_permanencia(horas=360.0, es_liberado=True)  # 15 días

    # Assert - Liberado
    assert sev_lib_baja == SeveridadAlerta.BAJA
    assert sev_lib_media == SeveridadAlerta.MEDIA
    assert sev_lib_alta == SeveridadAlerta.ALTA
    assert sev_lib_critica == SeveridadAlerta.CRITICA


@pytest.mark.asyncio
async def test_auditoria_solicitudes_mapeo_dict_sin_fecha_asignacion(db_session):
    """
    Verifica que el servicio de supervisión pueda mapear correctamente filas agregadas en dict
    (PostgreSQL CTE) donde los mecánicos no tienen fecha_asignacion o tienen campos parciales,
    sin lanzar ValidationError.
    """
    from datetime import datetime
    mock_row = {
        "id": 999,
        "n_bus": "BUS-999",
        "bus_id": 1,
        "bus_patente": "ABCD12",
        "usuario_creador_id": 1,
        "usuario_creador_nombre": "Test Conductor",
        "mecanico_cierre_id": None,
        "mecanico_cierre_nombre": None,
        "estado": "EN_REPARACION",
        "descripcion_general": "Falla prueba",
        "foto_url": None,
        "motivo_incompleto_checklist": None,
        "motivo_cierre_parcial": None,
        "fecha_creacion": datetime.now(),
        "fecha_cierre": None,
        "fecha_liberacion": None,
        "horas_en_taller": 2.5,
        "reincidencias_30d": 0,
        "total_fallas": 1,
        "fallas_resueltas": 0,
        "fallas_pendientes": 1,
        "fallas_con_falta_repuesto": 0,
        "detalles_json": [],
        "mecanicos_json": [
            {
                "id": 10,
                "solicitud_id": 999,
                "mecanico_id": 5,
                "mecanico_nombre": "Juan Mecanico",
                "es_lider_responsable": False,
                "is_activo": True,
                # fecha_asignacion omitida intencionalmente para validar resiliencia
            }
        ],
        "historial_mecanicos_json": [],
        "comentarios_json": [],
        "pauta_respuestas_json": [],
    }

    mock_repo = MagicMock(spec=SupervisionRepository)
    mock_repo.get_auditoria = AsyncMock(return_value=[mock_row])

    service = SupervisionService(repository=mock_repo)
    dtos = await service.get_auditoria_solicitudes(db_session, n_bus="BUS-999")

    assert len(dtos) == 1
    assert isinstance(dtos[0], SolicitudResumenDTO)
    assert dtos[0].id == 999
    assert dtos[0].n_bus == "BUS-999"
    assert dtos[0].estado == "EN_REPARACION"
    assert dtos[0].chofer == "Test Conductor"
    assert dtos[0].tiempo_taller == 2.5
    assert dtos[0].numero_fallas == 1
    # Validar que los campos innecesarios no existen en el DTO ultraligero
    assert not hasattr(dtos[0], "bus_patente")
    assert not hasattr(dtos[0], "bus_id")
    assert not hasattr(dtos[0], "descripcion_general")
    assert not hasattr(dtos[0], "foto_url")
    assert not hasattr(dtos[0], "comentarios")
    assert not hasattr(dtos[0], "mecanicos")



