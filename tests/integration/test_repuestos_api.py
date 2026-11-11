"""Flujo de catálogo y trazabilidad de repuestos por falla."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle


@pytest.mark.asyncio
async def test_repuestos_bitacora_y_anulacion(client, db_session, seed_test_data, auth_headers_supervisor, auth_headers_conductor):
    # Arrange
    ot = TallerSolicitud(n_bus="REP-TEST", es_ot=True, estado="PENDIENTE")
    db_session.add(ot)
    await db_session.flush()
    falla = TallerSolicitudDetalle(solicitud_id=ot.id, estado_revision="APROBADA", descripcion_personalizada="Fuga de aire")
    db_session.add(falla)
    await db_session.commit()
    ruta = f"/api/v1/taller/{ot.id}/detalles/{falla.id}/repuestos-utilizados"
    creado = await client.post("/api/v1/taller/repuestos", headers=auth_headers_supervisor, json={"codigo": "ABC", "nombre": "Válvula", "unidad": "UN", "precio": "10", "iva": "1.9"})
    assert creado.status_code == 201, creado.text
    repuesto = creado.json()
    payload = {"repuesto_id": repuesto["id"], "cantidad": "2", "operacion_id": str(uuid4())}

    # Act
    registrado = await client.post(ruta, headers=auth_headers_supervisor, json=payload)
    assert registrado.status_code == 201, registrado.text
    repetido = await client.post(ruta, headers=auth_headers_supervisor, json=payload)
    assert repetido.status_code == 200, repetido.text
    registro_id = registrado.json()["id"]
    anulado = await client.patch(f"{ruta}/{registro_id}/anulacion", headers=auth_headers_supervisor, json={"motivo": "Error", "operacion_id": str(uuid4())})
    assert anulado.status_code == 200, anulado.text
    repetido_tardio = await client.post(ruta, headers=auth_headers_supervisor, json=payload)
    assert repetido_tardio.status_code == 200, repetido_tardio.text
    listado = await client.get(ruta, headers=auth_headers_supervisor)

    # Assert
    assert listado.status_code == 200 and listado.json() == []
    comentarios = (await db_session.scalars(select(TallerSolicitudComentario).where(TallerSolicitudComentario.solicitud_id == ot.id).order_by(TallerSolicitudComentario.id))).all()
    assert len(comentarios) == 2
    assert "Fuga de aire" in comentarios[0].comentario
    assert "[ABC] Válvula; cantidad: 2" in comentarios[0].comentario
    assert "Error" not in comentarios[1].comentario
    denegado = await client.get("/api/v1/taller/repuestos", headers=auth_headers_conductor)
    assert denegado.status_code == 403


@pytest.mark.asyncio
async def test_varios_repuestos_catalogo_editable_y_proteccion(client, db_session, seed_test_data, auth_headers_supervisor, auth_headers_mecanico1):
    ot = TallerSolicitud(n_bus="REP-MULTI", es_ot=True, estado="PENDIENTE")
    db_session.add(ot)
    await db_session.flush()
    falla = TallerSolicitudDetalle(solicitud_id=ot.id, estado_revision="APROBADA", descripcion_personalizada="Freno")
    db_session.add(falla)
    await db_session.commit()
    ruta = f"/api/v1/taller/{ot.id}/detalles/{falla.id}/repuestos-utilizados"
    vacio = await client.get(ruta, headers=auth_headers_supervisor)
    assert vacio.status_code == 200 and vacio.json() == []
    ids = []
    for codigo in ("REP-1", "REP-2"):
        r = await client.post("/api/v1/taller/repuestos", headers=auth_headers_supervisor, json={"codigo": codigo, "nombre": "Pieza " + codigo})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
        uso = await client.post(ruta, headers=auth_headers_supervisor, json={"repuesto_id": ids[-1], "cantidad": "1.5", "operacion_id": str(uuid4())})
        assert uso.status_code == 201, uso.text
    listado = await client.get(ruta, headers=auth_headers_supervisor)
    assert len(listado.json()) == 2
    sin_asignacion = await client.post(ruta, headers=auth_headers_mecanico1, json={"repuesto_id": ids[0], "cantidad": "1", "operacion_id": str(uuid4())})
    assert sin_asignacion.status_code == 403
    editado = await client.patch(f"/api/v1/taller/repuestos/{ids[0]}", headers=auth_headers_supervisor, json={"codigo": "EDITADO", "is_active": False})
    assert editado.status_code == 200 and editado.json()["id"] == ids[0]
    historial = await client.get(ruta, headers=auth_headers_supervisor)
    assert historial.json()[0]["codigo_repuesto_al_registrar"] == "REP-1"
    borrar = await client.delete(f"/api/v1/supervision/solicitudes/{ot.id}/detalles/{falla.id}", headers=auth_headers_supervisor)
    assert borrar.status_code == 422, borrar.text


@pytest.mark.asyncio
async def test_mecanico_asignado_registra_uso(client, db_session, seed_test_data, auth_headers_supervisor, auth_headers_mecanico1):
    ot = TallerSolicitud(n_bus="REP-MEC", es_ot=True, estado="PENDIENTE")
    db_session.add(ot)
    await db_session.flush()
    falla = TallerSolicitudDetalle(solicitud_id=ot.id, estado_revision="APROBADA", descripcion_personalizada="Luces")
    db_session.add(falla)
    await db_session.flush()
    db_session.add(TallerAsignacionFalla(solicitud_id=ot.id, detalle_id=falla.id, mecanico_id=seed_test_data["mecanico1"].id, origen="SUPERVISOR", is_activo=True))
    await db_session.commit()
    articulo = await client.post("/api/v1/taller/repuestos", headers=auth_headers_supervisor, json={"codigo": "L1", "nombre": "Lámpara"})
    assert articulo.status_code == 201, articulo.text
    respuesta = await client.post(f"/api/v1/taller/{ot.id}/detalles/{falla.id}/repuestos-utilizados", headers=auth_headers_mecanico1, json={"repuesto_id": articulo.json()["id"], "cantidad": "2", "operacion_id": str(uuid4())})
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["usuario_registro_id"] == seed_test_data["mecanico1"].id


