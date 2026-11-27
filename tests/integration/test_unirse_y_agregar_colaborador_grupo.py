from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import update

from app.core.security import create_access_token, get_password_hash
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico


async def _crear_usuario(db_session, *, user_id: int, nombre: str, apellido: str, username: str, rol_id: int):
    user = Usuario(
        id=user_id,
        nombre=nombre,
        apellido=apellido,
        username=username,
        password_hash=get_password_hash("password123"),
        rol_id=rol_id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token(subject=user_id)}"}


async def _crear_ot_con_dos_fallas(client, db_session, auth_headers_conductor, *, bus_id: int, n_bus: str, patente: str):
    bus = Bus(
        id=bus_id,
        n_bus=n_bus,
        patente=patente,
        marca="Scania",
        modelo="K400",
        is_active=True,
        en_taller=False,
    )
    db_session.add(bus)
    await db_session.commit()

    res = await client.post(
        "/api/v1/taller/solicitudes",
        json={
            "n_bus": n_bus,
            "descripcion_general": "Revisión grupal",
            "detalles": [
                {"falla_id": 1, "descripcion_personalizada": "Falla C"},
                {"falla_id": 2, "descripcion_personalizada": "Falla D"},
            ],
        },
        headers=auth_headers_conductor,
    )
    assert res.status_code == 201, res.text
    data = res.json()
    return data["id"], data["detalles"][0]["id"], data["detalles"][1]["id"]


@pytest.mark.asyncio
async def test_self_join_tardio_conserva_cronometria_original(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
    auth_headers_mecanico1,
):
    """Mecánico F se une 2h después a las fallas C y D donde trabajan A y B sin alterar sus tiempos."""
    _, headers_mec3 = await _crear_usuario(
        db_session,
        user_id=20,
        nombre="Felipe",
        apellido="Mecanico3",
        username="mecanico3@narbus.cl",
        rol_id=2,
    )
    sol_id, det_c, det_d = await _crear_ot_con_dos_fallas(
        client, db_session, auth_headers_conductor, bus_id=30, n_bus="401", patente="BC4001"
    )

    # A (id=2) y B (id=3) toman fallas C y D
    res_inicio = await client.post(
        f"/api/v1/taller/{sol_id}/autoasignar",
        json={"detalles_ids": [det_c, det_d], "colaboradores_ids": [3], "comentario": "Inicio A y B"},
        headers=auth_headers_mecanico1,
    )
    assert res_inicio.status_code == 200, res_inicio.text

    # Simular que A y B comenzaron hace 2 horas
    hace_2_horas = datetime.now(timezone.utc) - timedelta(hours=2)
    await db_session.execute(
        update(TallerAsignacionFalla)
        .where(TallerAsignacionFalla.solicitud_id == sol_id)
        .values(fecha_asignacion=hace_2_horas)
    )
    await db_session.execute(
        update(TallerSolicitudMecanico)
        .where(TallerSolicitudMecanico.solicitud_id == sol_id)
        .values(fecha_asignacion=hace_2_horas)
    )
    await db_session.commit()

    # F (id=20) se une en caliente con unirse_a_activas=True
    res_join = await client.post(
        f"/api/v1/taller/{sol_id}/autoasignar",
        json={"detalles_ids": [det_c, det_d], "unirse_a_activas": True, "comentario": "Apoyo en taller"},
        headers=headers_mec3,
    )
    assert res_join.status_code == 200, res_join.text
    data_join = res_join.json()

    activos_ot = {m["mecanico_id"]: m for m in data_join["mecanicos"] if m["is_activo"]}
    assert {2, 3, 20}.issubset(activos_ot.keys())

    for det_id in (det_c, det_d):
        det = next(d for d in data_join["detalles"] if d["id"] == det_id)
        asig_ids = {m["id"] for m in det["mecanicos_asignados"]}
        assert {2, 3, 20}.issubset(asig_ids)

    assert any("Se unió al equipo" in (c.get("comentario") or "") for c in data_join["comentarios"])

    # Terminar avance cierra con cronometría independiente: A y B ~120 min, F ~0 min
    res_fin = await client.post(
        f"/api/v1/taller/{sol_id}/terminar-avance",
        json={"comentario": "Cierre de turno"},
        headers=headers_mec3,
    )
    assert res_fin.status_code == 200, res_fin.text
    fin_data = res_fin.json()
    assert fin_data["mecanicos"] == []
    mecanicos_hist = {m["mecanico_id"]: m for m in fin_data["historial_mecanicos"]}
    assert mecanicos_hist[2]["duracion_minutos"] >= 115
    assert mecanicos_hist[3]["duracion_minutos"] >= 115
    assert mecanicos_hist[20]["duracion_minutos"] < 5


@pytest.mark.asyncio
async def test_self_join_validaciones_retrocompatibilidad_y_falla_resuelta(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
    auth_headers_mecanico1,
    auth_headers_mecanico2,
    taller_resultado,
):
    """Valida que sin flag siga bloqueando, que rechace fallas resueltas y re-unión duplicada."""
    sol_id, det_c, det_d = await _crear_ot_con_dos_fallas(
        client, db_session, auth_headers_conductor, bus_id=31, n_bus="402", patente="BC4002"
    )

    res_inicio = await client.post(
        f"/api/v1/taller/{sol_id}/autoasignar",
        json={"detalles_ids": [det_c, det_d]},
        headers=auth_headers_mecanico1,
    )
    assert res_inicio.status_code == 200, res_inicio.text

    # Sin unirse_a_activas (default False) mantiene 422
    res_sin_flag = await client.post(
        f"/api/v1/taller/{sol_id}/autoasignar",
        json={"detalles_ids": [det_c]},
        headers=auth_headers_mecanico2,
    )
    assert res_sin_flag.status_code == 422

    # Unirse a falla ya activa funciona; reintentar las mismas fallas falla con 422
    res_ok = await client.post(
        f"/api/v1/taller/{sol_id}/autoasignar",
        json={"detalles_ids": [det_c], "unirse_a_activas": True},
        headers=auth_headers_mecanico2,
    )
    assert res_ok.status_code == 200, res_ok.text

    res_dup = await client.post(
        f"/api/v1/taller/{sol_id}/autoasignar",
        json={"detalles_ids": [det_c], "unirse_a_activas": True},
        headers=auth_headers_mecanico2,
    )
    assert res_dup.status_code == 422

    # Resolver falla D y verificar que mecánico 2 no puede unirse a falla resuelta
    payload_res = await taller_resultado["payload"](sol_id, det_d, "RESUELTA", mecanicos_ids=[2])
    res_check = await client.patch(
        f"/api/v1/taller/{sol_id}/detalles/{det_d}/check",
        json=payload_res,
        headers=auth_headers_mecanico1,
    )
    assert res_check.status_code == 200, res_check.text

    res_resuelta = await client.post(
        f"/api/v1/taller/{sol_id}/autoasignar",
        json={"detalles_ids": [det_d], "unirse_a_activas": True},
        headers=auth_headers_mecanico2,
    )
    assert res_resuelta.status_code == 422
    assert "resuelta" in res_resuelta.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_agregar_colaborador_por_cualquier_integrante_y_rbac(
    client,
    db_session,
    seed_test_data,
    auth_headers_conductor,
    auth_headers_mecanico1,
    auth_headers_mecanico2,
):
    """Cualquier miembro activo del grupo puede añadir compañeros a fallas específicas o heredadas."""
    _, headers_mec3 = await _crear_usuario(
        db_session,
        user_id=21,
        nombre="Luis",
        apellido="Mecanico3",
        username="luis3@narbus.cl",
        rol_id=2,
    )
    _, headers_mec4 = await _crear_usuario(
        db_session,
        user_id=22,
        nombre="Mario",
        apellido="Mecanico4",
        username="mario4@narbus.cl",
        rol_id=2,
    )
    rol_visual = Rol(id=5, nombre="VISUAL", descripcion="Solo lectura")
    db_session.add(rol_visual)
    await db_session.commit()
    _, headers_visual = await _crear_usuario(
        db_session,
        user_id=23,
        nombre="Vera",
        apellido="Visual",
        username="visual@narbus.cl",
        rol_id=5,
    )

    sol_id, det_c, det_d = await _crear_ot_con_dos_fallas(
        client, db_session, auth_headers_conductor, bus_id=32, n_bus="403", patente="BC4003"
    )

    # Mecánico 1 invita a Mecánico 2 en Falla C y Falla D
    res_inicio = await client.post(
        f"/api/v1/taller/{sol_id}/autoasignar",
        json={"detalles_ids": [det_c, det_d], "colaboradores_ids": [3]},
        headers=auth_headers_mecanico1,
    )
    assert res_inicio.status_code == 200, res_inicio.text

    # Mecánico 2 (no líder) añade a Mecánico 3 explícitamente a fallas C y D
    res_add = await client.post(
        f"/api/v1/taller/{sol_id}/agregar-colaborador",
        json={"colaboradores_ids": [21], "detalles_ids": [det_c, det_d], "comentario": "Refuerzo en frenos"},
        headers=auth_headers_mecanico2,
    )
    assert res_add.status_code == 200, res_add.text
    data_add = res_add.json()
    for det_id in (det_c, det_d):
        det = next(d for d in data_add["detalles"] if d["id"] == det_id)
        mec3_asig = next(m for m in det["mecanicos_asignados"] if m["id"] == 21)
        assert mec3_asig["origen"] == "MECANICO"
    assert any("Incorporación al equipo" in (c.get("comentario") or "") for c in data_add["comentarios"])

    # Mecánico 3 añade a Mecánico 4 sin enviar detalles_ids -> hereda fallas activas de Mecánico 3
    res_add_auto = await client.post(
        f"/api/v1/taller/{sol_id}/agregar-colaborador",
        json={"colaboradores_ids": [22]},
        headers=headers_mec3,
    )
    assert res_add_auto.status_code == 200, res_add_auto.text
    for det_id in (det_c, det_d):
        det = next(d for d in res_add_auto.json()["detalles"] if d["id"] == det_id)
        assert any(m["id"] == 22 for m in det["mecanicos_asignados"])

    # Mecánico fuera del equipo no puede usar agregar-colaborador -> 422
    _, headers_mec5 = await _crear_usuario(
        db_session,
        user_id=24,
        nombre="Oscar",
        apellido="Externo",
        username="oscar5@narbus.cl",
        rol_id=2,
    )
    res_externo = await client.post(
        f"/api/v1/taller/{sol_id}/agregar-colaborador",
        json={"colaboradores_ids": [22], "detalles_ids": [det_c]},
        headers=headers_mec5,
    )
    assert res_externo.status_code == 422

    # RBAC: CONDUCTOR y VISUAL bloqueados (403) en ambos endpoints
    for hdrs in (auth_headers_conductor, headers_visual):
        r1 = await client.post(
            f"/api/v1/taller/{sol_id}/autoasignar",
            json={"detalles_ids": [det_c], "unirse_a_activas": True},
            headers=hdrs,
        )
        assert r1.status_code == 403
        r2 = await client.post(
            f"/api/v1/taller/{sol_id}/agregar-colaborador",
            json={"colaboradores_ids": [21], "detalles_ids": [det_c]},
            headers=hdrs,
        )
        assert r2.status_code == 403
