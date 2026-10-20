from uuid import uuid4

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("modulo", ["taller", "supervision/solicitudes"])
async def test_api_asigna_grupo_con_un_comentario(
    client, seed_test_data, auth_headers_conductor, auth_headers_supervisor, modulo
):
    # Arrange: OT con dos fallas, sin asignaciones.
    creado = await client.post(
        "/api/v1/taller/solicitudes",
        headers=auth_headers_conductor,
        json={
            "n_bus": "GRUPO-BITACORA",
            "detalles": [{"nombre": "Sin A/C"}, {"nombre": "Freno largo"}],
        },
    )
    assert creado.status_code == 201
    solicitud = creado.json()
    mecanicos = [seed_test_data["mecanico1"], seed_test_data["mecanico2"]]
    ids = [m.id for m in mecanicos]
    detalles_ids = [d["id"] for d in solicitud["detalles"]]

    # Act: un envío grupal, incluso con IDs repetidos, crea un solo mensaje.
    asignado = await client.post(
        f"/api/v1/{modulo}/{solicitud['id']}/asignar",
        headers=auth_headers_supervisor,
        json={
            "mecanicos_ids": [*ids, ids[0]],
            "detalles_ids": [*detalles_ids, detalles_ids[0]],
            "comentario": "Viendo en fosa",
        },
    )

    # Assert: grupo completo en ambas fallas y observación única.
    assert asignado.status_code == 200, asignado.text
    data = asignado.json()
    assert data["estado"] == "EN_REPARACION"
    comentarios = [c for c in data["comentarios"] if c["tipo"] == "ASIGNACION"]
    assert len(comentarios) == 1
    texto = comentarios[0]["comentario"]
    assert all(m.nombre_completo in texto for m in mecanicos)
    assert seed_test_data["supervisor"].nombre_completo not in texto
    assert texto.count("Viendo en fosa") == 1
    assert texto.count("Sin A/C") == 1
    for detalle in data["detalles"]:
        assert {m["id"] for m in detalle["mecanicos_asignados"]} == set(ids)


@pytest.mark.asyncio
@pytest.mark.parametrize("modulo", ["taller", "supervision/solicitudes"])
@pytest.mark.parametrize("estado", ["RESUELTA", "INCOMPLETA", "PENDIENTE"])
async def test_estado_falla_texto_breve_con_nota_directa(
    client, seed_test_data, auth_headers_conductor, auth_headers_supervisor, modulo, estado
):
    # Arrange: ambos mecánicos comparten una falla.
    creado = await client.post(
        "/api/v1/taller/solicitudes", headers=auth_headers_conductor,
        json={"n_bus": "GRUPO-RESOLUCION", "detalles": [{"nombre": "Sin A/C"}]},
    )
    assert creado.status_code == 201
    solicitud = creado.json()
    id_ot = solicitud["id"]
    detalle_id = solicitud["detalles"][0]["id"]
    mecanicos = [seed_test_data["mecanico1"], seed_test_data["mecanico2"]]
    asignado = await client.post(
        f"/api/v1/taller/{id_ot}/asignar", headers=auth_headers_supervisor,
        json={"mecanicos_ids": [m.id for m in mecanicos], "detalles_ids": [detalle_id]},
    )
    assert asignado.status_code == 200
    ficha_inicial = await client.get(f"/api/v1/taller/{id_ot}", headers=auth_headers_supervisor)
    detalle_inicial = next(d for d in ficha_inicial.json()["detalles"] if d["id"] == detalle_id)
    ciudad = await client.post("/api/v1/taller/ciudades", headers=auth_headers_supervisor,
        json={"codigo": "SCL", "nombre": "Santiago"})
    assert ciudad.status_code == 201, ciudad.text
    taller = await client.post("/api/v1/taller/talleres", headers=auth_headers_supervisor,
        json={"nombre": "Taller de prueba", "ciudad_id": ciudad.json()["id"], "tipo": "INTERNO"})
    assert taller.status_code == 201, taller.text

    # Act: registrar estado y una nota distinta del motivo de incompletitud.
    response = await client.patch(
        f"/api/v1/{modulo}/{id_ot}/detalles/{detalle_id}/check",
        headers=auth_headers_supervisor,
        json={
            "operacion_id": str(uuid4()),
            "evento_esperado_id": detalle_inicial["evento_estado_vigente_id"],
            "estado": estado, "motivo_incompleto": "Falta prueba de ruta",
            "comentario": "Viendo en fosa",
            **({} if estado == "PENDIENTE" else {
                "mecanicos_ids": [m.id for m in mecanicos],
                "taller_id": taller.json()["id"],
            }),
        },
    )
    assert response.status_code == 200, response.text
    ficha = await client.get(f"/api/v1/taller/{id_ot}", headers=auth_headers_supervisor)

    # Assert: una nota directa, participantes esenciales y autor en metadatos.
    comentario = ficha.json()["comentarios"][-1]
    nombres = " y ".join(m.nombre_completo for m in mecanicos)
    esperado = {
        "RESUELTA": f"{nombres} repararon: Sin A/C. Viendo en fosa",
        "INCOMPLETA": "Incompleta: Sin A/C. Falta prueba de ruta. Viendo en fosa",
        "PENDIENTE": "Reapertura: Sin A/C. Viendo en fosa",
    }[estado]
    assert comentario["comentario"] == esperado
    assert comentario["usuario_id"] == seed_test_data["supervisor"].id
