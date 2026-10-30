import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.modules.auth.models.usuario import Usuario
from app.modules.taller.models.pauta_taller import PautaTallerItem
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario


@pytest.fixture
async def pauta_ot(db_session, seed_test_data):
    db_session.add_all([
        PautaTallerItem(id=i, categoria="General", item=f"Punto {i}", orden=i, is_active=i < 4)
        for i in range(1, 5)
    ])
    solicitud = TallerSolicitud(n_bus="TEST-PAUTA", es_ot=True, usuario_creador_id=1)
    db_session.add(solicitud)
    await db_session.commit()
    return solicitud.id


@pytest.mark.parametrize("rol", ["supervisor", "admin"])
async def test_gestion_pauta_y_resumen(
    client, db_session, pauta_ot, auth_headers_supervisor, auth_headers_mecanico1, rol,
):
    # Arrange: misma pauta para dos roles autorizados y catálogo de tres puntos activos.
    headers = auth_headers_supervisor
    actor_id = 4
    if rol == "admin":
        db_session.add(Usuario(id=6, nombre="Ana", apellido="Admin", username="admin@test.cl",
                              password_hash=get_password_hash("password123"), rol_id=4, is_active=True))
        await db_session.commit()
        actor_id = 6
        headers = {"Authorization": f"Bearer {create_access_token(subject=actor_id)}"}
    url = f"/api/v1/supervision/solicitudes/{pauta_ot}/pauta"
    inicial = await client.get(url, headers=headers)
    assert inicial.status_code == 200, inicial.text
    assert inicial.json()["resumen"] == {"revisadas": 0, "total": 3}
    assert len(inicial.json()["puntos"]) == 3
    assert all(not punto["revisado"] for punto in inicial.json()["puntos"])

    # Act: registrar y luego corregir/desmarcar parcialmente, conservando el punto omitido.
    guardado = await client.patch(url, headers=headers, json={"puntos": [
        {"item_id": 1, "estado": "OK", "mecanico_id": 2},
        {"item_id": 2, "estado": "DEFECTO", "observacion": "Fuga", "mecanico_id": 3},
        {"item_id": 3, "estado": "NO_APLICA", "mecanico_id": 2},
    ]})
    assert guardado.status_code == 200, guardado.text
    assert guardado.json()["resumen"] == {"revisadas": 3, "total": 3}
    assert guardado.json()["puntos"][0]["respuesta"]["mecanico_id"] == 2
    assert guardado.json()["puntos"][0]["respuesta"]["mecanico_nombre"] == "Pedro Mecanico"
    assert guardado.json()["puntos"][1]["respuesta"]["mecanico_id"] == 3
    completa = await client.get(f"/api/v1/supervision/solicitudes/{pauta_ot}", headers=headers)
    assert completa.status_code == 200, completa.text
    assert completa.json()["pauta_completada"] is True
    cambio = await client.patch(url, headers=headers, json={"puntos": [
        {"item_id": 1, "estado": None}, {"item_id": 2, "estado": "OK", "mecanico_id": 2},
    ]})
    assert cambio.status_code == 200, cambio.text

    # Assert: resumen dinámico, pendientes explícitos, trazabilidad y contrato anterior vigente.
    assert cambio.json()["resumen"] == {"revisadas": 2, "total": 3}
    assert cambio.json()["puntos"][0]["respuesta"] is None
    assert cambio.json()["puntos"][1]["respuesta"]["estado"] == "OK"
    assert cambio.json()["puntos"][1]["respuesta"]["mecanico_id"] == 2
    assert cambio.json()["puntos"][2]["respuesta"]["estado"] == "NO_APLICA"
    ficha = await client.get(f"/api/v1/supervision/solicitudes/{pauta_ot}", headers=headers)
    assert ficha.status_code == 200, ficha.text
    assert ficha.json()["pauta_resumen"] == {"revisadas": 2, "total": 3}
    assert ficha.json()["pauta_completada"] is False
    assert "pauta_respuestas" not in ficha.json()
    legacy = await client.get(f"/api/v1/taller/{pauta_ot}/pauta", headers=auth_headers_mecanico1)
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["respondidos"] == 2
    comentarios = (await db_session.execute(select(TallerSolicitudComentario).where(
        TallerSolicitudComentario.solicitud_id == pauta_ot,
    ))).scalars().all()
    assert len(comentarios) == 2
    assert all(comentario.usuario_id == actor_id for comentario in comentarios)
    assert "PENDIENTE" in comentarios[-1].comentario
    assert "Pedro Mecanico (ID 2)" in comentarios[-1].comentario
    assert "Carlos Mecanico (ID 3)" in comentarios[0].comentario


@pytest.mark.parametrize("headers_fixture", ["auth_headers_conductor", "auth_headers_mecanico1"])
async def test_gestion_pauta_restringida(client, pauta_ot, request, headers_fixture):
    headers = request.getfixturevalue(headers_fixture)
    url = f"/api/v1/supervision/solicitudes/{pauta_ot}/pauta"
    assert (await client.get(url, headers=headers)).status_code == 403
    assert (await client.patch(url, headers=headers, json={"puntos": [
        {"item_id": 1, "estado": "OK"},
    ]})).status_code == 403


@pytest.mark.parametrize("puntos,status", [
    ([], 422),
    ([{"item_id": 1, "estado": "INVALIDO"}], 422),
    ([{"item_id": 1}], 422),
    ([{"item_id": 1, "estado": None, "observacion": "Fuga"}], 422),
    ([{"item_id": 1, "estado": "OK"}, {"item_id": 1, "estado": None}], 422),
    ([{"item_id": 1, "estado": "OK", "mecanico_id": 2}, {"item_id": 999, "estado": "OK", "mecanico_id": 2}], 404),
    ([{"item_id": 4, "estado": "OK", "mecanico_id": 2}], 404),
    ([{"item_id": 1, "estado": "OK"}], 422),
    ([{"item_id": 1, "estado": "OK", "mecanico_id": 4}], 422),
    ([{"item_id": 1, "estado": "OK", "mecanico_id": 999}], 422),
    ([{"item_id": 1, "estado": None, "mecanico_id": 2}], 422),
])
async def test_gestion_invalida_atomica(client, pauta_ot, auth_headers_supervisor, puntos, status):
    url = f"/api/v1/supervision/solicitudes/{pauta_ot}/pauta"
    response = await client.patch(url, headers=auth_headers_supervisor, json={"puntos": puntos})
    assert response.status_code == status, response.text
    estado = await client.get(url, headers=auth_headers_supervisor)
    assert estado.json()["resumen"]["revisadas"] == 0


async def test_pauta_inexistente_y_sin_token(client, auth_headers_supervisor):
    url = "/api/v1/supervision/solicitudes/99999/pauta"
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers=auth_headers_supervisor)).status_code == 404
    assert (await client.patch(url, headers=auth_headers_supervisor, json={"puntos": [
        {"item_id": 1, "estado": "OK", "mecanico_id": 2},
    ]})).status_code == 404


async def test_desmarcar_es_idempotente(client, pauta_ot, auth_headers_supervisor):
    url = f"/api/v1/supervision/solicitudes/{pauta_ot}/pauta"
    for _ in range(2):
        response = await client.patch(url, headers=auth_headers_supervisor,
                                      json={"puntos": [{"item_id": 1, "estado": None}]})
        assert response.status_code == 200, response.text
        assert response.json()["resumen"] == {"revisadas": 0, "total": 3}


async def test_catalogo_vacio(client, db_session, seed_test_data, auth_headers_supervisor):
    solicitud = TallerSolicitud(n_bus="PAUTA-VACIA", es_ot=True, usuario_creador_id=1)
    db_session.add(solicitud)
    await db_session.commit()
    detalle = await client.get(f"/api/v1/supervision/solicitudes/{solicitud.id}",
                               headers=auth_headers_supervisor)
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["pauta_resumen"] == {"revisadas": 0, "total": 0}
    assert detalle.json()["pauta_completada"] is False
    pauta = await client.get(f"/api/v1/supervision/solicitudes/{solicitud.id}/pauta",
                             headers=auth_headers_supervisor)
    assert pauta.status_code == 200, pauta.text
    assert pauta.json()["puntos"] == []


async def test_revisor_inactivo_rechaza_lote_completo(
    client, db_session, pauta_ot, seed_test_data, auth_headers_supervisor,
):
    seed_test_data["mecanico2"].is_active = False
    await db_session.commit()
    url = f"/api/v1/supervision/solicitudes/{pauta_ot}/pauta"
    response = await client.patch(url, headers=auth_headers_supervisor, json={"puntos": [
        {"item_id": 1, "estado": "OK", "mecanico_id": 2},
        {"item_id": 2, "estado": "OK", "mecanico_id": 3},
    ]})
    assert response.status_code == 422, response.text
    estado = await client.get(url, headers=auth_headers_supervisor)
    assert estado.json()["resumen"]["revisadas"] == 0


async def test_lista_mecanicos_para_selector(client, seed_test_data, auth_headers_supervisor):
    response = await client.get("/api/v1/auth/mecanicos?q=Pedro&skip=0&limit=20",
                                headers=auth_headers_supervisor)
    assert response.status_code == 200, response.text
    assert response.headers["X-Total-Count"] == "1"
    assert response.json()[0]["id"] == 2
    assert response.json()[0]["nombre_completo"] == "Pedro Mecanico"


async def test_varios_revisores_reemplazo_y_desmarcado(client, db_session, pauta_ot, auth_headers_supervisor):
    from app.modules.taller.models.pauta_taller import TallerSolicitudPautaMecanico

    url = f"/api/v1/supervision/solicitudes/{pauta_ot}/pauta"
    guardado = await client.patch(url, headers=auth_headers_supervisor, json={"puntos": [
        {"item_id": 1, "estado": "OK", "mecanicos_ids": [3, 2]},
    ]})
    assert guardado.status_code == 200, guardado.text
    respuesta = guardado.json()["puntos"][0]["respuesta"]
    assert respuesta["mecanicos_ids"] == [2, 3]
    assert respuesta["mecanicos"] == [{"id": 2, "nombre": "Pedro Mecanico"}, {"id": 3, "nombre": "Carlos Mecanico"}]
    assert guardado.json()["resumen"]["revisadas"] == 1
    detalle = await client.get(f"/api/v1/taller/{pauta_ot}", headers=auth_headers_supervisor)
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["pauta_respuestas"][0]["mecanicos_ids"] == [2, 3]
    corregido = await client.patch(url, headers=auth_headers_supervisor, json={"puntos": [
        {"item_id": 1, "estado": "DEFECTO", "mecanicos_ids": [3]},
    ]})
    assert corregido.status_code == 200, corregido.text
    assert corregido.json()["puntos"][0]["respuesta"]["mecanicos_ids"] == [3]
    borrado = await client.patch(url, headers=auth_headers_supervisor, json={"puntos": [
        {"item_id": 1, "estado": None},
    ]})
    assert borrado.status_code == 200, borrado.text
    assert borrado.json()["puntos"][0]["respuesta"] is None
    assert (await db_session.execute(select(TallerSolicitudPautaMecanico))).scalars().all() == []


@pytest.mark.parametrize("ids", [[], [2, 2], [0], [-1], [2, 4], [2, 999]])
async def test_revisores_multiples_invalidos(client, pauta_ot, auth_headers_supervisor, ids):
    url = f"/api/v1/supervision/solicitudes/{pauta_ot}/pauta"
    response = await client.patch(url, headers=auth_headers_supervisor, json={"puntos": [
        {"item_id": 1, "estado": "OK", "mecanicos_ids": ids},
    ]})
    assert response.status_code == 422, response.text
    assert (await client.get(url, headers=auth_headers_supervisor)).json()["resumen"]["revisadas"] == 0


async def test_mecanico_con_equipo_solo_se_registra_a_si_mismo(
    client, db_session, pauta_ot, auth_headers_mecanico1, auth_headers_supervisor,
):
    from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico

    db_session.add_all([
        TallerSolicitudMecanico(solicitud_id=pauta_ot, mecanico_id=mid, is_activo=True)
        for mid in (2, 3)
    ])
    await db_session.commit()
    response = await client.post(f"/api/v1/taller/{pauta_ot}/pauta", headers=auth_headers_mecanico1,
                                 json={"respuestas": [{"item_id": 1, "estado": "OK"}]})
    assert response.status_code == 200, response.text
    assert response.json()["respuestas"][0]["mecanicos_ids"] == [2]
    pauta = await client.get(f"/api/v1/supervision/solicitudes/{pauta_ot}/pauta", headers=auth_headers_supervisor)
    assert pauta.json()["puntos"][0]["respuesta"]["mecanicos_ids"] == [2]
