import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.mantencion.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta


@pytest.mark.asyncio
async def test_fase1_models_and_schema_integrity(db_session: AsyncSession):
    """
    Verifica la creación e integridad relacional de los modelos de la Fase 1:
    - Campo en_taller en Bus.
    - Campos motivo_incompleto_checklist y motivo_cierre_parcial en TallerSolicitud.
    - Campos falta_repuesto y comentario_repuesto en TallerSolicitudDetalle.
    - Campos asignado_por_id y duracion_minutos en TallerSolicitudMecanico.
    - Asignación atómica y co-responsabilidad multi-mecánico en TallerAsignacionFalla.
    - Catálogo PautaTallerItem y respuestas TallerSolicitudPauta.
    """
    # 1. Crear roles y usuarios (supervisor y 2 mecánicos)
    rol_sup = Rol(nombre="Supervisor", descripcion="Supervisa taller")
    rol_mec = Rol(nombre="Mecanico", descripcion="Reparaciones taller")
    db_session.add_all([rol_sup, rol_mec])
    await db_session.flush()

    supervisor = Usuario(
        username="supervisora_test",
        password_hash="hash",
        nombre="Carla",
        apellido="Soto",
        rol_id=rol_sup.id,
    )
    mecanico_1 = Usuario(
        username="mecanico1_test",
        password_hash="hash",
        nombre="Juan",
        apellido="Perez",
        rol_id=rol_mec.id,
    )
    mecanico_2 = Usuario(
        username="mecanico2_test",
        password_hash="hash",
        nombre="Pedro",
        apellido="Gomez",
        rol_id=rol_mec.id,
    )

    db_session.add_all([supervisor, mecanico_1, mecanico_2])
    await db_session.flush()

    # 2. Crear Bus con en_taller por defecto False
    bus = Bus(
        patente="ABCD12",
        n_bus="305",
        marca="Scania",
        modelo="K400",
        en_taller=False,
    )
    db_session.add(bus)
    await db_session.flush()
    assert bus.en_taller is False

    # 3. Crear Categoría y Falla
    cat = CategoriaFalla(nombre="Motor")
    db_session.add(cat)
    await db_session.flush()

    falla = FallaTaller(categoria_id=cat.id, nombre="Fuga de aceite")
    db_session.add(falla)
    await db_session.flush()

    # 4. Crear Solicitud y Detalle con soporte para repuestos
    solicitud = TallerSolicitud(
        n_bus=bus.n_bus,
        bus_id=bus.id,
        usuario_creador_id=supervisor.id,
        estado="REPORTADO",
        descripcion_general="Revision completa de motor",
        motivo_incompleto_checklist=None,
        motivo_cierre_parcial=None,
    )
    db_session.add(solicitud)
    await db_session.flush()

    detalle_1 = TallerSolicitudDetalle(
        solicitud_id=solicitud.id,
        falla_id=falla.id,
        descripcion_personalizada="Gotea aceite por empaquetadura",
        falta_repuesto=True,
        comentario_repuesto="Falta empaquetadura de carter",
    )
    db_session.add(detalle_1)
    await db_session.flush()
    assert detalle_1.falta_repuesto is True
    assert detalle_1.comentario_repuesto == "Falta empaquetadura de carter"

    # 5. Co-responsabilidad: 2 mecánicos asignados a la MISMA falla (detalle_1)
    asig_mec1 = TallerAsignacionFalla(
        solicitud_id=solicitud.id,
        detalle_id=detalle_1.id,
        mecanico_id=mecanico_1.id,
        asignado_por_id=supervisor.id,
        origen="SUPERVISOR",
        is_activo=True,
    )
    asig_mec2 = TallerAsignacionFalla(
        solicitud_id=solicitud.id,
        detalle_id=detalle_1.id,
        mecanico_id=mecanico_2.id,
        asignado_por_id=mecanico_2.id,
        origen="AUTOASIGNACION",
        is_activo=True,
    )
    db_session.add_all([asig_mec1, asig_mec2])
    await db_session.flush()

    # 6. Registrar presencia en taller_solicitud_mecanicos con asignado_por_id y duracion_minutos
    part_mec1 = TallerSolicitudMecanico(
        solicitud_id=solicitud.id,
        mecanico_id=mecanico_1.id,
        asignado_por_id=supervisor.id,
        duracion_minutos=120,
        is_activo=True,
    )
    db_session.add(part_mec1)
    await db_session.flush()

    # 7. Pauta de Taller
    pauta_item = PautaTallerItem(
        categoria="NIVELES Y FLUIDOS",
        item="Nivel de aceite de motor",
        orden=1,
        is_active=True,
    )
    db_session.add(pauta_item)
    await db_session.flush()

    respuesta_pauta = TallerSolicitudPauta(
        solicitud_id=solicitud.id,
        item_id=pauta_item.id,
        estado="DEFECTO",
        observacion="Bajo nivel por fuga detectada",
        mecanico_id=mecanico_1.id,
    )
    db_session.add(respuesta_pauta)
    await db_session.commit()

    # 8. Verificaciones de consulta
    result_asig = await db_session.execute(
        select(TallerAsignacionFalla).where(TallerAsignacionFalla.detalle_id == detalle_1.id)
    )
    asignaciones = result_asig.scalars().all()
    assert len(asignaciones) == 2
    mecanicos_ids = {a.mecanico_id for a in asignaciones}
    assert mecanico_1.id in mecanicos_ids
    assert mecanico_2.id in mecanicos_ids

    result_pauta = await db_session.execute(
        select(TallerSolicitudPauta).where(TallerSolicitudPauta.solicitud_id == solicitud.id)
    )
    pautas = result_pauta.scalars().all()
    assert len(pautas) == 1
    assert pautas[0].estado == "DEFECTO"
    assert pautas[0].item.item == "Nivel de aceite de motor"
