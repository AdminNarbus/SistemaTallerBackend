import pytest

from app.modules.taller.models.taller_solicitud import TallerSolicitud


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", [None, "", "   ", "SOLICITUD", " reportado ",
                                  "PENDIENTE", " en_reparacion ", "LIBERADO", "FINALIZADO"])
async def test_auditoria_filtra_tipo_estado_y_total(
    client, db_session, auth_headers_supervisor, seed_test_data, estado
):
    solicitudes = [
        TallerSolicitud(n_bus=f"FILTRO-{i}", es_ot=es_ot, estado=operativo,
                       usuario_creador_id=seed_test_data["conductor"].id)
        for i, (es_ot, operativo) in enumerate([
            (False, "REPORTADO"), (False, "PENDIENTE"),
            (True, "PENDIENTE"), (True, "EN_REPARACION"),
            (True, "LIBERADO"), (True, "FINALIZADO"),
        ])
    ]
    db_session.add_all(solicitudes)
    await db_session.commit()
    normalizado = estado.strip().upper() if estado else ""
    esperadas = [s.id for s in solicitudes if (
        not normalizado
        or (normalizado in ("SOLICITUD", "REPORTADO") and not s.es_ot)
        or (normalizado not in ("SOLICITUD", "REPORTADO") and s.es_ot and s.estado == normalizado)
    )]
    params = {"n_bus": "FILTRO-", "limit": 1}
    if estado is not None:
        params["estado"] = estado
    recibidas = []
    for skip in range(len(esperadas) + 1):
        response = await client.get(
            "/api/v1/supervision/auditoria/buses-taller",
            params={**params, "skip": skip}, headers=auth_headers_supervisor,
        )
        assert response.status_code == 200, response.text
        assert int(response.headers["X-Total-Count"]) == len(esperadas)
        recibidas.extend(row["id"] for row in response.json())
    assert sorted(recibidas) == sorted(esperadas)
