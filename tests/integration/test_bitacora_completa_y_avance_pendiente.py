"""Contrato del chat global y del cierre de avance sin resolver fallas."""

import pytest

from app.modules.taller.constants import TipoComentarioBitacora


@pytest.fixture
async def solicitud_bitacora(client, auth_headers_conductor):
    respuesta = await client.post(
        "/api/v1/taller/solicitudes",
        headers=auth_headers_conductor,
        json={
            "n_bus": "BUS-BITACORA",
            "detalles": [{"nombre": "Puerta cabina"}, {"nombre": "Vigias"}],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("con_colaborador", [False, True])
@pytest.mark.parametrize("seleccion", ["explicita", "omitida", "vacia"])
async def test_terminar_avance_conserva_fallas_pendientes(
    client, solicitud_bitacora, auth_headers_mecanico1, con_colaborador, seleccion,
):
    # Arrange: dos fallas pendientes con asignaciones individuales o compartidas.
    url = f"/api/v1/taller/{solicitud_bitacora['id']}"
    detalles_ids = [detalle["id"] for detalle in solicitud_bitacora["detalles"]]
    asignacion = await client.post(
        url + "/autoasignar", headers=auth_headers_mecanico1,
        json={"detalles_ids": detalles_ids, "colaboradores_ids": [3] if con_colaborador else []},
    )
    assert asignacion.status_code == 200, asignacion.text
    mensaje_previo = await client.post(
        url + "/comentarios", headers=auth_headers_mecanico1,
        json={"comentario": "Diagnostico previo que debe permanecer en la bitacora"},
    )
    assert mensaje_previo.status_code == 200, mensaje_previo.text
    comentario_previo_id = mensaje_previo.json()["comentario_id"]

    # Act: finalizar la atención sin enviar un check de resultado.
    nota = "Falta rotor corto; queda pendiente para el siguiente turno"
    payload = {"comentario": nota}
    if seleccion != "omitida":
        payload["detalles_ids"] = detalles_ids if seleccion == "explicita" else []
    respuesta = await client.post(
        url + "/terminar-avance", headers=auth_headers_mecanico1,
        json=payload,
    )
    assert respuesta.status_code == 200, respuesta.text
    ficha = await client.get(url, headers=auth_headers_mecanico1)
    assert ficha.status_code == 200, ficha.text

    # Assert: las copias de la nota por asignación producen un solo mensaje global.
    for datos in (respuesta.json(), ficha.json()):
        assert comentario_previo_id in [c["id"] for c in datos["comentarios"]]
        assert datos["estado"] == "PENDIENTE"
        assert datos["mecanicos"] == []
        for detalle in datos["detalles"]:
            assert detalle["estado"] == "PENDIENTE"
            assert detalle["resuelto"] is False
            assert detalle["motivo_incompleto"] is None
            assert detalle["mecanicos_asignados"] == []
            assert len(detalle["historial_avances"]) == 1
            avance = detalle["historial_avances"][0]
            assert nota in avance["comentario"]
            assert avance["usuario_id"] == 2
            for asignacion in detalle["historial_asignaciones"]:
                assert asignacion["comentario"] is None
                assert asignacion["comentario_avance_id"] == avance["id"]
                assert asignacion["fecha_desasignacion"] == avance["fecha_registro"]
                assert asignacion["is_activo"] is False
                assert asignacion["fecha_desasignacion"] is not None
                assert asignacion["duracion_minutos"] is not None
        mensajes = [c for c in datos["comentarios"] if nota in c["comentario"]]
        assert len(mensajes) == 1
        assert mensajes[0]["tipo"] == "ENTREGA_TURNO"


@pytest.mark.asyncio
async def test_terminar_avance_cierra_grupo_aunque_llegue_seleccion_parcial(
    client, solicitud_bitacora, auth_headers_mecanico1,
):
    # Arrange: dos fallas atendidas por el mismo equipo.
    url = f"/api/v1/taller/{solicitud_bitacora['id']}"
    primera, segunda = [detalle["id"] for detalle in solicitud_bitacora["detalles"]]
    asignacion = await client.post(
        url + "/autoasignar", headers=auth_headers_mecanico1,
        json={"detalles_ids": [primera, segunda], "colaboradores_ids": [3]},
    )
    assert asignacion.status_code == 200, asignacion.text

    # Act: un cliente legado envía una selección parcial.
    nota = "Cierre de todo el equipo"
    respuesta = await client.post(
        url + "/terminar-avance", headers=auth_headers_mecanico1,
        json={"detalles_ids": [primera], "comentario": nota},
    )
    assert respuesta.status_code == 200, respuesta.text
    ficha = await client.get(url, headers=auth_headers_mecanico1)
    assert ficha.status_code == 200, ficha.text

    # Assert: se cierra todo el equipo y cada falla recibe un único avance.
    for datos in (respuesta.json(), ficha.json()):
        assert datos["estado"] == "PENDIENTE"
        assert datos["mecanicos"] == []
        detalles = {detalle["id"]: detalle for detalle in datos["detalles"]}
        assert detalles[primera]["mecanicos_asignados"] == []
        assert detalles[segunda]["mecanicos_asignados"] == []
        for detalle in detalles.values():
            assert len(detalle["historial_avances"]) == 1
            for asignacion in detalle["historial_asignaciones"]:
                assert asignacion["is_activo"] is False
                assert asignacion["comentario"] is None
        mensajes = [c for c in datos["comentarios"] if nota in c["comentario"]]
        assert len(mensajes) == 1
        assert mensajes[0]["usuario_id"] == 2


@pytest.mark.asyncio
async def test_terminar_avance_rechaza_fallas_de_otra_ot_sin_modificar_ot(
    client, solicitud_bitacora, auth_headers_mecanico1,
):
    # Arrange: el mecánico solo está atendiendo la primera falla.
    url = f"/api/v1/taller/{solicitud_bitacora['id']}"
    primera, segunda = [detalle["id"] for detalle in solicitud_bitacora["detalles"]]
    asignacion = await client.post(
        url + "/autoasignar", headers=auth_headers_mecanico1,
        json={"detalles_ids": [primera]},
    )
    assert asignacion.status_code == 200, asignacion.text
    antes = await client.get(url, headers=auth_headers_mecanico1)
    assert antes.status_code == 200, antes.text

    # Act: intentar atribuir un avance a una falla sin asignación propia activa.
    respuesta = await client.post(
        url + "/terminar-avance", headers=auth_headers_mecanico1,
        json={"detalles_ids": [999999], "comentario": "No debe guardarse"},
    )

    # Assert: no cambia el estado, ni las asignaciones, ni la bitácora.
    assert respuesta.status_code == 422, respuesta.text
    despues = await client.get(url, headers=auth_headers_mecanico1)
    assert despues.status_code == 200, despues.text
    for campo in ("estado", "mecanicos", "detalles", "comentarios", "fecha_actualizacion"):
        assert despues.json()[campo] == antes.json()[campo]


@pytest.mark.asyncio
async def test_integrante_sin_falla_propia_cierra_asignaciones_de_toda_la_cuadrilla(
    client, solicitud_bitacora, auth_headers_mecanico1, auth_headers_mecanico2,
):
    # Arrange: un mecánico tiene presencia y el otro una falla asignada.
    url = f"/api/v1/taller/{solicitud_bitacora['id']}"
    presencia = await client.post(url + "/tomar", headers=auth_headers_mecanico1, json={})
    assert presencia.status_code == 200, presencia.text
    asignacion = await client.post(
        url + "/autoasignar", headers=auth_headers_mecanico2,
        json={"detalles_ids": [solicitud_bitacora["detalles"][0]["id"]]},
    )
    assert asignacion.status_code == 200, asignacion.text

    # Act: el integrante que solo tiene presencia cierra el avance del grupo.
    respuesta = await client.post(
        url + "/terminar-avance", headers=auth_headers_mecanico1,
        json={"comentario": "Termino de apoyo general"},
    )

    # Assert: se cierra también la asignación del compañero, conservando el historial.
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["estado"] == "PENDIENTE"
    assert datos["mecanicos"] == []
    assert all(not d["mecanicos_asignados"] for d in datos["detalles"])
    ids_previos = {c["id"] for c in asignacion.json()["comentarios"]}
    assert ids_previos.issubset({c["id"] for c in datos["comentarios"]})


@pytest.mark.asyncio
async def test_chat_global_incluye_todos_los_tipos_sin_deduplicar_por_texto(
    client, solicitud_bitacora, auth_headers_mecanico1,
):
    # Arrange: mensajes del mismo texto y de todos los tipos admitidos.
    url = f"/api/v1/taller/{solicitud_bitacora['id']}"
    tipos = [tipo.value for tipo in TipoComentarioBitacora] + ["GENERAL"]
    ids_creados = []
    for tipo in tipos:
        respuesta = await client.post(
            url + "/comentarios", headers=auth_headers_mecanico1,
            json={"tipo": tipo, "comentario": "Observacion repetida intencionalmente"},
        )
        assert respuesta.status_code == 200, respuesta.text
        ids_creados.append(respuesta.json()["comentario_id"])

    # Act: consultar la fuente completa del chat de la OT.
    respuesta = await client.get(url, headers=auth_headers_mecanico1)
    assert respuesta.status_code == 200, respuesta.text
    mensajes = [c for c in respuesta.json()["comentarios"] if c["id"] in ids_creados]

    # Assert: cada mensaje mantiene su identidad incluso si coincide texto y autor.
    assert [c["id"] for c in mensajes] == ids_creados
    assert [c["tipo"] for c in mensajes] == tipos
    assert len(set(ids_creados)) == len(tipos)


@pytest.mark.asyncio
async def test_observaciones_de_falla_aparecen_una_vez_en_chat_global(
    client, solicitud_bitacora, auth_headers_mecanico1, taller_resultado,
):
    # Arrange: un mecánico atiende una falla y comunica un repuesto faltante.
    solicitud_id = solicitud_bitacora["id"]
    detalle_id = solicitud_bitacora["detalles"][0]["id"]
    url = f"/api/v1/taller/{solicitud_id}"
    asignacion = await client.post(
        url + "/autoasignar", headers=auth_headers_mecanico1,
        json={"detalles_ids": [detalle_id]},
    )
    assert asignacion.status_code == 200, asignacion.text
    repuesto = await client.patch(
        url + f"/detalles/{detalle_id}/repuesto", headers=auth_headers_mecanico1,
        json={"falta_repuesto": True, "comentario": "Esperando rotor corto"},
    )
    assert repuesto.status_code == 200, repuesto.text

    # Act: registrar y reintentar la misma operación técnica de avance incompleto.
    payload = await taller_resultado["payload"](
        solicitud_id, detalle_id, "INCOMPLETA", comentario="Se reviso el bombin",
    )
    for _ in range(2):
        resultado = await client.patch(
            url + f"/detalles/{detalle_id}/check", headers=auth_headers_mecanico1,
            json=payload,
        )
        assert resultado.status_code == 200, resultado.text
    respuesta = await client.get(url, headers=auth_headers_mecanico1)
    assert respuesta.status_code == 200, respuesta.text

    # Assert: ambas notas técnicas están en la bitácora, sin duplicar el reintento.
    comentarios = respuesta.json()["comentarios"]
    for tipo, nota in (("FALTA_REPUESTO", "Esperando rotor corto"), ("AVANCE", "Se reviso el bombin")):
        mensajes = [c for c in comentarios if nota in c["comentario"]]
        assert len(mensajes) == 1
        assert mensajes[0]["tipo"] == tipo
