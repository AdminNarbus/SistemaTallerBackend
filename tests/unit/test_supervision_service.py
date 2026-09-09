import pytest
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
from app.modules.supervision.services import supervision_service
from app.modules.supervision.repository import supervision_repository


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
