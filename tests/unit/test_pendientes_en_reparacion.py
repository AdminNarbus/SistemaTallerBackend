from datetime import datetime, timezone
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.taller.constants import EstadoSolicitud
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.services.taller_service import taller_service


@pytest.mark.asyncio
async def test_list_pendientes_incluye_en_reparacion_y_excluye_reportado(
    db_session: AsyncSession, seed_test_data
):
    """
    Regla de Negocio:
    En la pestaña de 'Pendientes' del mecánico:
    - Deben aparecer las solicitudes en estado PENDIENTE.
    - Deben aparecer las solicitudes en estado EN_REPARACION.
    - NO deben aparecer solicitudes en estado REPORTADO (estado legado obsoleto).
    - NO deben aparecer solicitudes en estado LIBERADO ni FINALIZADO.
    """
    # ARRANGE
    ahora = datetime.now(timezone.utc)
    sol_pendiente = TallerSolicitud(
        n_bus="101",
        usuario_creador_id=1,
        estado=EstadoSolicitud.PENDIENTE.value,
        descripcion_general="Bus pendiente de asignación",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    sol_en_reparacion = TallerSolicitud(
        n_bus="102",
        usuario_creador_id=1,
        estado=EstadoSolicitud.EN_REPARACION.value,
        descripcion_general="Bus en reparación por cuadrilla",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    sol_reportado = TallerSolicitud(
        n_bus="103",
        usuario_creador_id=1,
        estado=EstadoSolicitud.REPORTADO.value,
        descripcion_general="Bus en estado legado reportado",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    sol_liberado = TallerSolicitud(
        n_bus="104",
        usuario_creador_id=1,
        estado=EstadoSolicitud.LIBERADO.value,
        descripcion_general="Bus liberado a ruta",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    sol_finalizado = TallerSolicitud(
        n_bus="105",
        usuario_creador_id=1,
        estado=EstadoSolicitud.FINALIZADO.value,
        descripcion_general="Bus finalizado completamente",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    db_session.add_all(
        [
            sol_pendiente,
            sol_en_reparacion,
            sol_reportado,
            sol_liberado,
            sol_finalizado,
        ]
    )
    await db_session.flush()

    # Agregar detalle de falla sin resolver a la orden en reparación
    det = TallerSolicitudDetalle(
        solicitud_id=sol_en_reparacion.id,
        descripcion_personalizada="Cambio de pastillas de freno",
        resuelto=False,
    )
    db_session.add(det)
    await db_session.commit()

    # ACT
    pendientes = await taller_service.list_pendientes(db_session)
    total_count = await taller_service.count_pendientes(db_session)

    # ASSERT
    buses_visibles = [p.n_bus for p in pendientes]
    assert "101" in buses_visibles, "OT PENDIENTE debe ser visible"
    assert "102" in buses_visibles, "OT EN_REPARACION debe ser visible"
    assert "103" not in buses_visibles, "OT REPORTADO no debe ser visible"
    assert "104" not in buses_visibles, "OT LIBERADO no debe ser visible"
    assert "105" not in buses_visibles, "OT FINALIZADO no debe ser visible"
    assert len(pendientes) == 2
    assert total_count == 2

    # Validar que los estados preservan su valor canónico en el DTO resumen
    dto_en_rep = next(p for p in pendientes if p.n_bus == "102")
    assert dto_en_rep.estado == "EN_REPARACION"
    assert dto_en_rep.numero_fallas == 1


@pytest.mark.asyncio
async def test_list_pendientes_filtro_opcional_estado(
    db_session: AsyncSession, seed_test_data
):
    """
    Valida que el parámetro opcional `estado` filtre exactamente el estado solicitado
    (e.g., solo 'PENDIENTE' o solo 'EN_REPARACION').
    """
    # ARRANGE
    ahora = datetime.now(timezone.utc)
    sol1 = TallerSolicitud(
        n_bus="201",
        usuario_creador_id=1,
        estado=EstadoSolicitud.PENDIENTE.value,
        descripcion_general="Pendiente",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    sol2 = TallerSolicitud(
        n_bus="202",
        usuario_creador_id=1,
        estado=EstadoSolicitud.EN_REPARACION.value,
        descripcion_general="En Reparacion",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    db_session.add_all([sol1, sol2])
    await db_session.commit()

    # ACT & ASSERT - Filtro PENDIENTE
    res_pendiente = await taller_service.list_pendientes(db_session, estado="PENDIENTE")
    count_pendiente = await taller_service.count_pendientes(db_session, estado="PENDIENTE")
    assert len(res_pendiente) == 1
    assert res_pendiente[0].n_bus == "201"
    assert count_pendiente == 1

    # ACT & ASSERT - Filtro EN_REPARACION
    res_en_rep = await taller_service.list_pendientes(db_session, estado="EN_REPARACION")
    count_en_rep = await taller_service.count_pendientes(db_session, estado="EN_REPARACION")
    assert len(res_en_rep) == 1
    assert res_en_rep[0].n_bus == "202"
    assert count_en_rep == 1


@pytest.mark.asyncio
async def test_endpoint_get_pendientes_mecanico(
    client, db_session: AsyncSession, seed_test_data, auth_headers_mecanico1
):
    """
    Valida que el endpoint HTTP GET /api/v1/taller/pendientes responda 200 OK,
    con cabecera X-Total-Count correcta y conteniendo tanto PENDIENTE como EN_REPARACION.
    """
    # ARRANGE
    ahora = datetime.now(timezone.utc)
    s1 = TallerSolicitud(
        n_bus="301",
        usuario_creador_id=1,
        estado=EstadoSolicitud.PENDIENTE.value,
        descripcion_general="OT Pendiente",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    s2 = TallerSolicitud(
        n_bus="302",
        usuario_creador_id=1,
        estado=EstadoSolicitud.EN_REPARACION.value,
        descripcion_general="OT En Reparacion",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    s3 = TallerSolicitud(
        n_bus="303",
        usuario_creador_id=1,
        estado=EstadoSolicitud.REPORTADO.value,
        descripcion_general="OT Reportada Antigua",
        fecha_creacion=ahora,
        fecha_actualizacion=ahora,
    )
    db_session.add_all([s1, s2, s3])
    await db_session.commit()

    # ACT
    response = await client.get("/api/v1/taller/pendientes", headers=auth_headers_mecanico1)

    # ASSERT
    assert response.status_code == 200
    data = response.json()
    assert response.headers.get("X-Total-Count") == "2"
    assert len(data) == 2
    buses = [d["n_bus"] for d in data]
    assert "301" in buses
    assert "302" in buses
    assert "303" not in buses

