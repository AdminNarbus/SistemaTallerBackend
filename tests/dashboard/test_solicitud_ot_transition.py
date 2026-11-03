"""Regression del intervalo solicitud → OT y de las solicitudes aún sin OT."""

import pytest
from sqlalchemy import insert, update
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.modules.dashboard.repository.relations import C, D, S
from tests.dashboard.conftest import at


@pytest.mark.asyncio
async def test_transition_keeps_both_dates_and_excludes_legacy_response(dashboard_client, dashboard_data):
    db = dashboard_data
    await db.execute(update(S).values(es_ot=True))
    await db.execute(update(S).where(S.c.id == 2).values(es_ot=False))
    await db.execute(insert(C).values(
        solicitud_id=3,
        usuario_id=1001,
        tipo="SISTEMA",
        comentario="Solicitud aprobada como OT. Mecánico asignado.",
        fecha_registro=at("2026-10-25T13:00"),
    ))
    await db.commit()

    indicators = (await dashboard_client.get("/api/v1/dashboard/indicadores")).json()["data"]
    assert indicators["estados"]["solicitadas_buses"] == 1
    assert indicators["tiempos"]["respuesta"]["validos"] == 1
    assert indicators["tiempos"]["respuesta"]["mediana_horas"] == 1

    response = await dashboard_client.get("/api/v1/dashboard/solicitudes?tabla_ot=2")
    assert response.status_code == 200
    row = response.json()["data"]["items"][0]
    assert row["estado"] == "SOLICITADO"
    assert row["es_ot"] is False
    assert row["fecha_creacion_ot"] is None

    response = await dashboard_client.get("/api/v1/dashboard/solicitudes?tabla_ot=3")
    row = response.json()["data"]["items"][0]
    assert row["fecha_creacion_ot"].startswith("2026-10-25T13:00")

    timeline = await dashboard_client.get("/api/v1/dashboard/buses/102/cronologia")
    assert timeline.status_code == 200
    stages = timeline.json()["data"]["items"]
    assert any(stage["tipo_evento"] == "SOLICITUD" and stage["solicitud_id"] == 3 for stage in stages)
    assert any(stage["tipo_evento"] == "CREACION_OT" and stage["solicitud_id"] == 3 for stage in stages)


@pytest.mark.asyncio
async def test_current_month_includes_faults_reported_before_ot(dashboard_client, dashboard_data):
    local_noon = datetime.now(ZoneInfo("America/Santiago")).replace(
        day=1, hour=12, minute=0, second=0, microsecond=0
    ).astimezone(timezone.utc)
    await dashboard_data.execute(update(S).where(S.c.id == 2).values(
        es_ot=False, fecha_creacion=local_noon
    ))
    await dashboard_data.execute(update(D).where(D.c.solicitud_id == 2).values(
        fecha_reporte=local_noon
    ))
    await dashboard_data.commit()

    response = await dashboard_client.get("/api/v1/dashboard/indicadores?solicitud_id=2")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mensuales"]["ot_totales"] == 1
    assert data["mensuales"]["ot_atendidas"] == 0
    assert data["mensuales"]["fallas_reportadas"] == 2
    assert data["mensuales"]["fallas_atendidas"] == 1
