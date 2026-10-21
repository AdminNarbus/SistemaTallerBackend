import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.modules.buses.models.bus import Bus
from app.modules.taller.constants import EstadoFalla, EstadoSolicitud
from app.modules.taller.dtos import EditarFallaDTO
from app.modules.taller.models.falla_taller import FallaTaller
from app.modules.taller.models.categoria_falla import CategoriaFalla
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_evidencia import TallerSolicitudEvidencia
from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.supervision.services import supervision_service


@pytest.mark.asyncio
async def test_eliminar_falla_duplicada_exitoso(db_session, seed_test_data):
    """Verifica que el supervisor pueda eliminar una avería duplicada con un solo clic y quede registrado en bitácora."""
    conductor = seed_test_data["conductor"]
    supervisor = seed_test_data["supervisor"]
    now = datetime.now(timezone.utc)

    # 1. Sembrar bus y solicitud con 2 fallas (una duplicada)
    bus = Bus(id=8801, n_bus="881", patente="DUP881", marca="Scania", modelo="K400", is_active=True, en_taller=True)
    db_session.add(bus)

    sol = TallerSolicitud(
        id=8801,
        n_bus="881",
        bus_id=8801,
        usuario_creador_id=conductor.id,
        estado=EstadoSolicitud.PENDIENTE.value,
        descripcion_general="Reporte inicial",
        fecha_creacion=now,
        fecha_actualizacion=now,
    )
    db_session.add(sol)

    det1 = TallerSolicitudDetalle(
        id=9901,
        solicitud_id=8801,
        descripcion_personalizada="Luces bajas quemadas",
        estado=EstadoFalla.PENDIENTE.value,
        resuelto=False,
        fecha_creacion=now,
    )
    det2 = TallerSolicitudDetalle(
        id=9902,
        solicitud_id=8801,
        descripcion_personalizada="Luces bajas quemadas",  # Duplicada
        estado=EstadoFalla.PENDIENTE.value,
        resuelto=False,
        fecha_creacion=now,
    )
    db_session.add_all([det1, det2])
    await db_session.commit()

    # 2. Ejecutar eliminación de falla duplicada
    result = await supervision_service.eliminar_falla(
        db_session,
        solicitud_id=8801,
        detalle_id=9902,
        supervisor_id=supervisor.id,
        supervisor_nombre="Supervisora Laura",
    )

    # 3. Asserts
    assert len(result.detalles) == 1
    assert result.detalles[0].id == 9901

    # Verificar bitácora
    comentarios = [c for c in result.comentarios if "por duplicidad" in c.comentario]
    assert len(comentarios) >= 1
    assert "Se elimina falla 'Luces bajas quemadas' por duplicidad" in comentarios[0].comentario

    # Verificar que en BD no exista det2
    det2_db = await db_session.get(TallerSolicitudDetalle, 9902)
    assert det2_db is None


@pytest.mark.asyncio
async def test_eliminar_falla_bloqueada_si_resuelta(db_session, seed_test_data):
    """Verifica que no se permita eliminar una falla que ya ha sido resuelta sin previa reapertura."""
    conductor = seed_test_data["conductor"]
    supervisor = seed_test_data["supervisor"]
    mecanico = seed_test_data["mecanico1"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        id=8802,
        n_bus="882",
        usuario_creador_id=conductor.id,
        estado=EstadoSolicitud.EN_REPARACION.value,
        fecha_creacion=now,
    )
    db_session.add(sol)

    det = TallerSolicitudDetalle(
        id=9903,
        solicitud_id=8802,
        descripcion_personalizada="Falla de frenos ya reparada",
        estado=EstadoFalla.RESUELTA.value,
        resuelto=True,
        mecanico_resolvio_id=mecanico.id,
        fecha_creacion=now,
        fecha_resolucion=now,
    )
    db_session.add(det)
    await db_session.commit()

    with pytest.raises(BusinessRuleException) as exc_info:
        await supervision_service.eliminar_falla(
            db_session,
            solicitud_id=8802,
            detalle_id=9903,
            supervisor_id=supervisor.id,
            supervisor_nombre="Supervisora Laura",
        )
    assert "marcada como resuelta" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_eliminar_falla_bloqueada_en_ot_finalizada(db_session, seed_test_data):
    """Verifica que no se puedan eliminar averías de una orden de trabajo finalizada."""
    conductor = seed_test_data["conductor"]
    supervisor = seed_test_data["supervisor"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        id=8803,
        n_bus="883",
        usuario_creador_id=conductor.id,
        estado=EstadoSolicitud.FINALIZADO.value,
        fecha_creacion=now,
    )
    db_session.add(sol)

    det = TallerSolicitudDetalle(
        id=9904,
        solicitud_id=8803,
        descripcion_personalizada="Avería pendiente antigua",
        estado=EstadoFalla.PENDIENTE.value,
        resuelto=False,
        fecha_creacion=now,
    )
    db_session.add(det)
    await db_session.commit()

    with pytest.raises(BusinessRuleException) as exc_info:
        await supervision_service.eliminar_falla(
            db_session,
            solicitud_id=8803,
            detalle_id=9904,
            supervisor_id=supervisor.id,
        )
    assert "orden que ya ha sido finalizada" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_editar_falla_con_justificacion_exitoso(db_session, seed_test_data):
    """Verifica que el supervisor pueda corregir el texto de una avería dejando justificación en bitácora."""
    conductor = seed_test_data["conductor"]
    supervisor = seed_test_data["supervisor"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        id=8804,
        n_bus="884",
        usuario_creador_id=conductor.id,
        estado=EstadoSolicitud.PENDIENTE.value,
        fecha_creacion=now,
    )
    db_session.add(sol)

    det = TallerSolicitudDetalle(
        id=9905,
        solicitud_id=8804,
        descripcion_personalizada="lucs no predn",
        estado=EstadoFalla.PENDIENTE.value,
        resuelto=False,
        fecha_creacion=now,
    )
    db_session.add(det)
    await db_session.commit()

    dto = EditarFallaDTO(
        descripcion_personalizada="Luces delanteras principales no encienden",
        justificacion="Corrección de redacción del chofer para claridad técnica",
    )

    result = await supervision_service.editar_falla(
        db_session,
        solicitud_id=8804,
        detalle_id=9905,
        dto=dto,
        supervisor_id=supervisor.id,
        supervisor_nombre="Supervisora Laura",
    )

    # Verificar descripción actualizada en DTO
    det_editado = next((d for d in result.detalles if d.id == 9905), None)
    assert det_editado is not None
    assert det_editado.descripcion_personalizada == "Luces delanteras principales no encienden"

    # Verificar bitácora inmutable
    comentario = next((c for c in result.comentarios if "modificada:" in c.comentario), None)
    assert comentario is not None
    assert "de 'lucs no predn' a 'Luces delanteras principales no encienden'" in comentario.comentario
    assert "Justificación: Corrección de redacción del chofer para claridad técnica" in comentario.comentario


@pytest.mark.asyncio
async def test_eliminar_evidencia_inicial_exitoso_y_ajuste_portada(db_session, seed_test_data):
    """Verifica la eliminación de una foto errónea del chofer y el ajuste dinámico de la foto de portada."""
    conductor = seed_test_data["conductor"]
    supervisor = seed_test_data["supervisor"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        id=8805,
        n_bus="885",
        usuario_creador_id=conductor.id,
        estado=EstadoSolicitud.PENDIENTE.value,
        foto_url="https://storage.narbus.cl/fotos/foto_borrosa.jpg",
        fecha_creacion=now,
    )
    db_session.add(sol)

    ev1 = TallerSolicitudEvidencia(
        id=7701,
        solicitud_id=8805,
        usuario_id=conductor.id,
        url="https://storage.narbus.cl/fotos/foto_borrosa.jpg",
        comentario_id=None,
        detalle_id=None,
        fecha_creacion=now,
    )
    ev2 = TallerSolicitudEvidencia(
        id=7702,
        solicitud_id=8805,
        usuario_id=conductor.id,
        url="https://storage.narbus.cl/fotos/foto_buena.jpg",
        comentario_id=None,
        detalle_id=None,
        fecha_creacion=now,
    )
    db_session.add_all([ev1, ev2])
    await db_session.commit()

    with patch("app.modules.taller.services.solicitud_service.storage_service.delete_file", new_callable=AsyncMock) as mock_del:
        mock_del.return_value = True

        result = await supervision_service.eliminar_evidencia_inicial(
            db_session,
            solicitud_id=8805,
            evidencia_id=7701,
            supervisor_id=supervisor.id,
            supervisor_nombre="Supervisora Laura",
        )

        mock_del.assert_called_once_with("https://storage.narbus.cl/fotos/foto_borrosa.jpg")

    # Verificar que solo quede ev2
    assert len(result.evidencias) == 1
    assert result.evidencias[0].id == 7702

    # Verificar que foto_url ahora apunte a ev2
    assert result.foto_url == "https://storage.narbus.cl/fotos/foto_buena.jpg"

    # Verificar bitácora
    comentario = next((c for c in result.comentarios if "Se elimina una imagen" in c.comentario), None)
    assert comentario is not None

    # Verificar en BD
    ev1_db = await db_session.get(TallerSolicitudEvidencia, 7701)
    assert ev1_db is None


@pytest.mark.asyncio
async def test_eliminar_evidencia_bloqueada_si_es_de_bitacora_o_falla(db_session, seed_test_data):
    """Verifica que las evidencias de bitácora o resolución no puedan ser eliminadas con este endpoint."""
    conductor = seed_test_data["conductor"]
    supervisor = seed_test_data["supervisor"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        id=8806,
        n_bus="886",
        usuario_creador_id=conductor.id,
        estado=EstadoSolicitud.PENDIENTE.value,
        fecha_creacion=now,
    )
    db_session.add(sol)

    ev_bitacora = TallerSolicitudEvidencia(
        id=7703,
        solicitud_id=8806,
        usuario_id=conductor.id,
        url="https://storage.narbus.cl/fotos/foto_bitacora.jpg",
        comentario_id=555,  # Vinculada a bitácora
        detalle_id=None,
        fecha_creacion=now,
    )
    ev_resolucion = TallerSolicitudEvidencia(
        id=7704,
        solicitud_id=8806,
        usuario_id=conductor.id,
        url="https://storage.narbus.cl/fotos/foto_check.jpg",
        comentario_id=None,
        detalle_id=666,  # Vinculada a falla
        fecha_creacion=now,
    )
    db_session.add_all([ev_bitacora, ev_resolucion])
    await db_session.commit()

    # Intentar eliminar foto de bitácora
    with pytest.raises(BusinessRuleException) as exc_b:
        await supervision_service.eliminar_evidencia_inicial(
            db_session,
            solicitud_id=8806,
            evidencia_id=7703,
            supervisor_id=supervisor.id,
        )
    assert "bitácora o comentarios" in str(exc_b.value).lower()

    # Intentar eliminar foto de resolución
    with pytest.raises(BusinessRuleException) as exc_r:
        await supervision_service.eliminar_evidencia_inicial(
            db_session,
            solicitud_id=8806,
            evidencia_id=7704,
            supervisor_id=supervisor.id,
        )
    assert "resolución de averías" in str(exc_r.value).lower()
