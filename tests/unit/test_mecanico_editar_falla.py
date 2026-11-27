import pytest
from datetime import datetime, timezone

from app.core.security import create_access_token
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.taller.constants import EstadoFalla, EstadoSolicitud
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle


@pytest.mark.asyncio
async def test_mecanico_edita_falla_propia_exitoso(
    client, db_session, seed_test_data, auth_headers_mecanico1,
):
    """El mecánico puede editar el texto de una falla abierta que él mismo reportó."""
    mecanico1 = seed_test_data["mecanico1"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        es_ot=True,
        id=9101,
        n_bus="911",
        usuario_creador_id=mecanico1.id,
        estado=EstadoSolicitud.EN_REPARACION.value,
        fecha_creacion=now,
    )
    det = TallerSolicitudDetalle(
        id=9201,
        solicitud_id=9101,
        descripcion_personalizada="Fuga en manguera de aire",
        estado=EstadoFalla.PENDIENTE.value,
        resuelto=False,
        reportado_por_id=mecanico1.id,
        fecha_creacion=now,
    )
    db_session.add_all([sol, det])
    await db_session.commit()

    nueva_desc = "Fuga severa en acople de manguera de aire trasera"
    response = await client.patch(
        "/api/v1/taller/9101/detalles/9201",
        headers=auth_headers_mecanico1,
        json={"descripcion_personalizada": nueva_desc},
    )

    assert response.status_code == 200, response.text
    solicitud = response.json()
    detalle = next(d for d in solicitud["detalles"] if d["id"] == 9201)
    assert detalle["descripcion_personalizada"] == nueva_desc
    comentario = next(c for c in solicitud["comentarios"] if c["tipo"] == "AVANCE")
    assert (
        comentario["comentario"]
        == f"Cambio de avería 'Fuga en manguera de aire' a '{nueva_desc}'."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("reportado_por_otro", [True, False], ids=["de-conductor", "sin-reportante"])
async def test_mecanico_puede_editar_falla_reportada_por_otro(
    client, db_session, seed_test_data, auth_headers_mecanico1, reportado_por_otro,
):
    """El mecánico puede editar una falla abierta aunque haya sido reportada por otro usuario o sin reportante."""
    conductor = seed_test_data["conductor"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        es_ot=True,
        id=9102 if reportado_por_otro else 9103,
        n_bus="912",
        usuario_creador_id=conductor.id,
        estado=EstadoSolicitud.EN_REPARACION.value,
        fecha_creacion=now,
    )
    det = TallerSolicitudDetalle(
        id=9202 if reportado_por_otro else 9203,
        solicitud_id=sol.id,
        descripcion_personalizada="Luz izquierda quemada",
        estado=EstadoFalla.PENDIENTE.value,
        resuelto=False,
        reportado_por_id=conductor.id if reportado_por_otro else None,
        fecha_creacion=now,
    )
    db_session.add_all([sol, det])
    await db_session.commit()

    nueva_desc = "Foco izquierdo sin iluminación"
    response = await client.patch(
        f"/api/v1/taller/{sol.id}/detalles/{det.id}",
        headers=auth_headers_mecanico1,
        json={"descripcion_personalizada": nueva_desc},
    )

    assert response.status_code == 200, response.text
    solicitud = response.json()
    detalle = next(d for d in solicitud["detalles"] if d["id"] == det.id)
    assert detalle["descripcion_personalizada"] == nueva_desc
    comentario = next(c for c in solicitud["comentarios"] if c["tipo"] == "AVANCE")
    assert (
        comentario["comentario"]
        == f"Cambio de avería 'Luz izquierda quemada' a '{nueva_desc}'."
    )


@pytest.mark.asyncio
async def test_mecanico_no_puede_editar_falla_resuelta(
    client, db_session, seed_test_data, auth_headers_mecanico1,
):
    """Una falla propia ya RESUELTA no se puede editar (422)."""
    mecanico1 = seed_test_data["mecanico1"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        es_ot=True,
        id=9104,
        n_bus="914",
        usuario_creador_id=mecanico1.id,
        estado=EstadoSolicitud.EN_REPARACION.value,
        fecha_creacion=now,
    )
    det = TallerSolicitudDetalle(
        id=9204,
        solicitud_id=9104,
        descripcion_personalizada="Cambio de filtro",
        estado=EstadoFalla.RESUELTA.value,
        resuelto=True,
        reportado_por_id=mecanico1.id,
        mecanico_resolvio_id=mecanico1.id,
        fecha_creacion=now,
        fecha_resolucion=now,
    )
    db_session.add_all([sol, det])
    await db_session.commit()

    response = await client.patch(
        "/api/v1/taller/9104/detalles/9204",
        headers=auth_headers_mecanico1,
        json={"descripcion_personalizada": "Cambio de filtro corregido"},
    )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_mecanico_no_puede_editar_falla_en_ot_finalizada(
    client, db_session, seed_test_data, auth_headers_mecanico1,
):
    """Una falla propia en una OT FINALIZADA no se puede editar (422)."""
    mecanico1 = seed_test_data["mecanico1"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        es_ot=True,
        id=9105,
        n_bus="915",
        usuario_creador_id=mecanico1.id,
        estado=EstadoSolicitud.FINALIZADO.value,
        fecha_creacion=now,
    )
    det = TallerSolicitudDetalle(
        id=9205,
        solicitud_id=9105,
        descripcion_personalizada="Revisión de freno",
        estado=EstadoFalla.PENDIENTE.value,
        resuelto=False,
        reportado_por_id=mecanico1.id,
        fecha_creacion=now,
    )
    db_session.add_all([sol, det])
    await db_session.commit()

    response = await client.patch(
        "/api/v1/taller/9105/detalles/9205",
        headers=auth_headers_mecanico1,
        json={"descripcion_personalizada": "Revisión de freno trasero"},
    )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_mecanico_no_puede_modificar_fecha_reporte(
    client, db_session, seed_test_data, auth_headers_mecanico1,
):
    """Un mecánico no tiene permiso para modificar fecha_reporte al editar su falla (403)."""
    mecanico1 = seed_test_data["mecanico1"]
    now = datetime.now(timezone.utc)

    sol = TallerSolicitud(
        es_ot=True,
        id=9106,
        n_bus="916",
        usuario_creador_id=mecanico1.id,
        estado=EstadoSolicitud.EN_REPARACION.value,
        fecha_creacion=now,
    )
    det = TallerSolicitudDetalle(
        id=9206,
        solicitud_id=9106,
        descripcion_personalizada="Ruido en tren delantero",
        estado=EstadoFalla.PENDIENTE.value,
        resuelto=False,
        reportado_por_id=mecanico1.id,
        fecha_creacion=now,
    )
    db_session.add_all([sol, det])
    await db_session.commit()

    response = await client.patch(
        "/api/v1/taller/9106/detalles/9206",
        headers=auth_headers_mecanico1,
        json={
            "descripcion_personalizada": "Ruido en rótula delantera derecha",
            "fecha_reporte": now.isoformat(),
        },
    )

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_conductor_y_visual_rechazados_en_editar_falla(
    client, db_session, seed_test_data, auth_headers_conductor,
):
    """CONDUCTOR y VISUAL reciben 403 al intentar editar una falla vía PATCH /taller/{id}/detalles/{detalle_id}."""
    conductor = seed_test_data["conductor"]
    now = datetime.now(timezone.utc)

    rol_visual = Rol(id=5, nombre="VISUAL", descripcion="Solo lectura")
    user_visual = Usuario(
        id=6,
        nombre="Inspector",
        apellido="Visual",
        username="visual@narbus.cl",
        password_hash="fakehash",
        rol_id=5,
        is_active=True,
    )
    sol = TallerSolicitud(
        es_ot=True,
        id=9107,
        n_bus="917",
        usuario_creador_id=conductor.id,
        estado=EstadoSolicitud.EN_REPARACION.value,
        fecha_creacion=now,
    )
    det = TallerSolicitudDetalle(
        id=9207,
        solicitud_id=9107,
        descripcion_personalizada="Falla test RBAC",
        estado=EstadoFalla.PENDIENTE.value,
        resuelto=False,
        reportado_por_id=conductor.id,
        fecha_creacion=now,
    )
    db_session.add_all([rol_visual, user_visual, sol, det])
    await db_session.commit()

    headers_visual = {"Authorization": f"Bearer {create_access_token(subject=6)}"}

    resp_conductor = await client.patch(
        "/api/v1/taller/9107/detalles/9207",
        headers=auth_headers_conductor,
        json={"descripcion_personalizada": "Edición conductor"},
    )
    resp_visual = await client.patch(
        "/api/v1/taller/9107/detalles/9207",
        headers=headers_visual,
        json={"descripcion_personalizada": "Edición visual"},
    )

    assert resp_conductor.status_code == 403, resp_conductor.text
    assert resp_visual.status_code == 403, resp_visual.text
