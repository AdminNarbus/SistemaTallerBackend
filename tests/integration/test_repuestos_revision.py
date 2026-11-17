"""Reglas de negocio y regresiones del ciclo completo de repuestos."""
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.modules.taller.models.repuesto import Repuesto
from app.modules.taller.models.taller_repuesto_utilizado import TallerRepuestoUtilizado
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario


@pytest.fixture
async def contexto_repuestos(client, db_session, auth_headers_supervisor):
    ot = TallerSolicitud(n_bus="REV-REP", es_ot=True, estado="LIBERADO")
    db_session.add(ot)
    await db_session.flush()
    falla = TallerSolicitudDetalle(solicitud_id=ot.id, estado_revision="APROBADA",
        descripcion_personalizada="Falla personalizada", falta_repuesto=True)
    db_session.add(falla)
    await db_session.commit()
    res = await client.post("/api/v1/taller/repuestos", headers=auth_headers_supervisor,
        json={"codigo": "0001-A", "nombre": "Válvula", "parte": "PT-100", "unidad": "UN", "precio": "10.1234", "iva": "1.9234"})
    assert res.status_code == 201, res.text
    return ot, falla, res.json(), f"/api/v1/taller/{ot.id}/detalles/{falla.id}/repuestos-utilizados"


def alta(repuesto_id, cantidad="1.2345", operacion_id=None):
    return {"repuesto_id": repuesto_id, "cantidad": cantidad, "operacion_id": operacion_id or str(uuid4())}


async def test_editar_id_cero_no_crea_articulo(client, db_session, auth_headers_supervisor):
    res = await client.patch("/api/v1/taller/repuestos/0", headers=auth_headers_supervisor,
        json={"codigo": "NO-CREAR", "nombre": "No debe existir"})
    assert res.status_code == 422, res.text
    assert await db_session.scalar(select(func.count()).select_from(Repuesto)) == 0


@pytest.mark.parametrize("cantidad", ["0", "-1", "NaN", "Infinity", "0.00001", "1000000000000", "abc"])
async def test_cantidades_invalidas(client, contexto_repuestos, auth_headers_supervisor, cantidad):
    ot, falla, repuesto, ruta = contexto_repuestos
    res = await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"], cantidad))
    assert res.status_code == 422, res.text


@pytest.mark.parametrize("campo,valor", [("codigo", None), ("nombre", None), ("is_active", None), ("codigo", "   "), ("precio", "-1"), ("iva", "-0.1")])
async def test_catalogo_rechaza_valores_invalidos(client, contexto_repuestos, auth_headers_supervisor, campo, valor):
    repuesto = contexto_repuestos[2]
    res = await client.patch(f"/api/v1/taller/repuestos/{repuesto['id']}", headers=auth_headers_supervisor, json={campo: valor})
    assert res.status_code == 422, res.text


@pytest.mark.parametrize("cambio", ["sin_ot", "finalizada", "sin_revision", "inactivo", "inexistente", "detalle_ajeno"])
async def test_rechazos_de_contexto(client, db_session, contexto_repuestos, auth_headers_supervisor, cambio):
    ot, falla, repuesto, ruta = contexto_repuestos
    esperado = 422
    if cambio == "sin_ot":
        ot.es_ot = False
    elif cambio == "finalizada":
        ot.estado = "FINALIZADO"
    elif cambio == "sin_revision":
        falla.estado_revision = "PENDIENTE"
    elif cambio == "inactivo":
        articulo = await db_session.get(Repuesto, repuesto["id"])
        articulo.is_active = False
        esperado = 404
    elif cambio == "inexistente":
        repuesto["id"] = 999999
        esperado = 404
    else:
        otra = TallerSolicitud(n_bus="OT-AJENA", es_ot=True, estado="PENDIENTE")
        db_session.add(otra)
        await db_session.flush()
        ruta = f"/api/v1/taller/{otra.id}/detalles/{falla.id}/repuestos-utilizados"
        esperado = 404
    await db_session.commit()
    res = await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"]))
    assert res.status_code == esperado, res.text
    assert await db_session.scalar(select(func.count()).select_from(TallerRepuestoUtilizado)) == 0


async def test_correccion_cantidad_historial_y_recibos(client, db_session, contexto_repuestos, auth_headers_supervisor):
    ot, falla, repuesto, ruta = contexto_repuestos
    datos = alta(repuesto["id"])
    res = await client.post(ruta, headers=auth_headers_supervisor, json=datos)
    assert res.status_code == 201, res.text
    original = res.json()
    mismo = await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"]))
    assert mismo.status_code == 200 and mismo.json()["id"] == original["id"]
    conflicto = await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"], "2", datos["operacion_id"]))
    assert conflicto.status_code == 409
    conflicto = await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"], "2"))
    assert conflicto.status_code == 409
    anular = {"motivo": "Corrección de cantidad", "operacion_id": str(uuid4())}
    url = f"{ruta}/{original['id']}/anulacion"
    res = await client.patch(url, headers=auth_headers_supervisor, json=anular)
    assert res.status_code == 200, res.text
    primera_anulacion = res.json()
    for payload in [anular, {"motivo": "Otro motivo", "operacion_id": str(uuid4())}]:
        res = await client.patch(url, headers=auth_headers_supervisor, json=payload)
        assert res.status_code == 200, res.text
        for campo in ("fecha_anulacion", "usuario_anulacion_id", "motivo_anulacion", "created_at"):
            assert res.json()[campo] == primera_anulacion[campo]
    res = await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"], "2.0001"))
    assert res.status_code == 201 and res.json()["id"] != original["id"]
    tardio = await client.post(ruta, headers=auth_headers_supervisor, json=datos)
    assert tardio.status_code == 200 and tardio.json()["id"] == original["id"]
    vigentes = await client.get(ruta, headers=auth_headers_supervisor)
    assert len(vigentes.json()) == 1
    assert Decimal(vigentes.json()[0]["cantidad_utilizada"]) == Decimal("2.0001")
    historial = await client.get(ruta + "?incluir_anulados=true", headers=auth_headers_supervisor)
    assert historial.headers["X-Total-Count"] == "2" and len(historial.json()) == 2
    assert historial.json()[0]["motivo_anulacion"] == "Corrección de cantidad"
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitudComentario)) == 3
    assert ot.estado == "LIBERADO" and falla.falta_repuesto is True and falla.resuelto is False


async def test_snapshots_catalogo_busqueda_paginacion(client, contexto_repuestos, auth_headers_supervisor, auth_headers_mecanico1):
    ot, falla, repuesto, ruta = contexto_repuestos
    res = await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"]))
    assert res.status_code == 201, res.text
    res = await client.patch(f"/api/v1/taller/repuestos/{repuesto['id']}", headers=auth_headers_supervisor,
        json={"codigo": "NUEVO", "nombre": "Nuevo nombre", "parte": "NUEVA", "unidad": "KIT", "is_active": False})
    assert res.status_code == 200, res.text
    listado = await client.get(ruta, headers=auth_headers_supervisor)
    uso = listado.json()[0]
    assert (uso["codigo_repuesto_al_registrar"], uso["nombre_repuesto_al_registrar"], uso["parte_repuesto_al_registrar"], uso["unidad_al_registrar"]) == ("0001-A", "Válvula", "PT-100", "UN")
    for q in ("NUEVO", "nombre", "NUEVA"):
        res = await client.get(f"/api/v1/taller/repuestos?q={q}&incluir_inactivos=true", headers=auth_headers_supervisor)
        assert res.headers["X-Total-Count"] == "1" and len(res.json()) == 1
    res = await client.get("/api/v1/taller/repuestos", headers=auth_headers_mecanico1)
    assert res.json() == []
    res = await client.get("/api/v1/taller/repuestos?incluir_inactivos=true", headers=auth_headers_mecanico1)
    assert res.status_code == 403
    res = await client.get(ruta + "?limit=1&skip=1", headers=auth_headers_supervisor)
    assert res.json() == [] and res.headers["X-Total-Count"] == "1"
    res = await client.get(f"/api/v1/taller/{ot.id}/repuestos-utilizados", headers=auth_headers_supervisor)
    assert len(res.json()) == 1 and res.json()[0]["n_bus"] == ot.n_bus


async def test_eventos_solo_en_mutaciones_y_commit(client, contexto_repuestos, auth_headers_supervisor):
    ot, falla, repuesto, ruta = contexto_repuestos
    datos = alta(repuesto["id"])
    with patch("app.modules.taller.services.repuesto_service.publish_event_soon") as emitir:
        res = await client.post(ruta, headers=auth_headers_supervisor, json=datos)
        assert res.status_code == 201, res.text
        assert emitir.call_count == 1
        evento = emitir.call_args.args[0]
        assert evento.resource_id == ot.id and evento.action == "REPUESTO_ALTA" and evento.version
        await client.post(ruta, headers=auth_headers_supervisor, json=datos)
        await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"]))
        assert emitir.call_count == 1
        url = f"{ruta}/{res.json()['id']}/anulacion"
        datos = {"motivo": "Error", "operacion_id": str(uuid4())}
        res = await client.patch(url, headers=auth_headers_supervisor, json=datos)
        assert res.status_code == 200, res.text
        assert emitir.call_count == 2 and emitir.call_args.args[0].action == "REPUESTO_ANULACION"
        await client.patch(url, headers=auth_headers_supervisor, json=datos)
        assert emitir.call_count == 2


async def test_permisos_de_autoria_y_anulacion(client, db_session, contexto_repuestos,
    auth_headers_supervisor, auth_headers_mecanico1, auth_headers_mecanico2, auth_headers_conductor):
    from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
    ot, falla, repuesto, ruta = contexto_repuestos
    for headers in (None, auth_headers_conductor, auth_headers_mecanico1):
        res = await client.post(ruta, headers=headers, json=alta(repuesto["id"]))
        assert res.status_code == (401 if headers is None else 403), res.text
    for headers in (auth_headers_conductor, auth_headers_mecanico1):
        res = await client.post("/api/v1/taller/repuestos", headers=headers, json={"codigo": "NO", "nombre": "NO"})
        assert res.status_code == 403, res.text
    db_session.add_all([TallerAsignacionFalla(solicitud_id=ot.id, detalle_id=falla.id,
        mecanico_id=uid, origen="SUPERVISOR", is_activo=True) for uid in (2, 3)])
    await db_session.commit()
    datos = alta(repuesto["id"])
    datos["usuario_registro_id"] = 3
    res = await client.post(ruta, headers=auth_headers_mecanico1, json=datos)
    assert res.status_code == 201, res.text
    assert res.json()["usuario_registro_id"] == 2
    registro_id = res.json()["id"]
    url = f"{ruta}/{registro_id}/anulacion"
    res = await client.patch(url, headers=auth_headers_mecanico2, json={"motivo": "Otro autor", "operacion_id": str(uuid4())})
    assert res.status_code == 403, res.text
    res = await client.patch(url, headers=auth_headers_mecanico1, json={"motivo": "   ", "operacion_id": str(uuid4())})
    assert res.status_code == 422, res.text
    res = await client.patch(url, headers=auth_headers_mecanico1, json={"motivo": "Propio", "operacion_id": str(uuid4())})
    assert res.status_code == 200, res.text
    assert res.json()["usuario_anulacion_id"] == 2
    eliminado = await client.delete(f"/api/v1/supervision/solicitudes/{ot.id}/detalles/{falla.id}", headers=auth_headers_supervisor)
    assert eliminado.status_code == 422, eliminado.text


async def test_rollback_atomico_de_alta(client, db_session, contexto_repuestos, auth_headers_supervisor):
    from unittest.mock import AsyncMock
    from sqlalchemy.exc import IntegrityError
    from app.modules.taller.models.taller_ubicacion import OperacionResultado
    ot, falla, repuesto, ruta = contexto_repuestos
    with patch("app.modules.taller.services.repuesto_service.taller_repository.touch_fecha_actualizacion",
        new=AsyncMock(side_effect=IntegrityError("fallo simulado", {}, Exception("integridad")))), patch(
        "app.modules.taller.services.repuesto_service.publish_event_soon") as emitir:
        res = await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"]))
        assert res.status_code == 409, res.text
        emitir.assert_not_called()
    for modelo in (TallerRepuestoUtilizado, TallerSolicitudComentario, OperacionResultado):
        assert await db_session.scalar(select(func.count()).select_from(modelo)) == 0


async def test_repuestos_en_falla_resuelta_y_ot_finalizada(client, db_session, contexto_repuestos, auth_headers_supervisor):
    ot, falla, repuesto, ruta = contexto_repuestos
    falla.estado = "RESUELTA"
    falla.resuelto = True
    await db_session.commit()
    datos = alta(repuesto["id"])
    res = await client.post(ruta, headers=auth_headers_supervisor, json=datos)
    assert res.status_code == 201, res.text
    registro_id = res.json()["id"]
    ot.estado = "FINALIZADO"
    await db_session.commit()
    res = await client.get(ruta, headers=auth_headers_supervisor)
    assert res.status_code == 200 and len(res.json()) == 1
    # El recibo original sigue disponible incluso después del cierre.
    res = await client.post(ruta, headers=auth_headers_supervisor, json=datos)
    assert res.status_code == 200, res.text
    res = await client.post(ruta, headers=auth_headers_supervisor, json=alta(repuesto["id"]))
    assert res.status_code == 422, res.text
    res = await client.patch(f"{ruta}/{registro_id}/anulacion", headers=auth_headers_supervisor,
        json={"motivo": "Error", "operacion_id": str(uuid4())})
    assert res.status_code == 422, res.text


async def test_catalogo_codigos_duplicados_y_recurso_inexistente(client, contexto_repuestos, auth_headers_supervisor):
    ot, falla, repuesto, ruta = contexto_repuestos
    res = await client.post("/api/v1/taller/repuestos", headers=auth_headers_supervisor,
        json={"codigo": " 0001-A ", "nombre": "Duplicado"})
    assert res.status_code == 409, res.text
    res = await client.patch("/api/v1/taller/repuestos/999999", headers=auth_headers_supervisor,
        json={"nombre": "No existe"})
    assert res.status_code == 404, res.text
    res = await client.get(ruta + "?limit=101", headers=auth_headers_supervisor)
    assert res.status_code == 422
    res = await client.get(ruta + "?skip=-1", headers=auth_headers_supervisor)
    assert res.status_code == 422


@pytest.mark.parametrize("rol", ["ADMIN", "VISUAL"])
async def test_admin_y_visual_respetan_permisos(client, db_session, contexto_repuestos, rol):
    from app.core.security import create_access_token
    from app.modules.auth.models.rol import Rol
    from app.modules.auth.models.usuario import Usuario
    if rol == "VISUAL":
        registro_rol = Rol(nombre="VISUAL")
        db_session.add(registro_rol)
        await db_session.flush()
        rol_id = registro_rol.id
    else:
        rol_id = 4
    usuario = Usuario(username=f"revision-{rol}", rol_id=rol_id, password_hash="test", is_active=True)
    db_session.add(usuario)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(subject=usuario.id)}"}
    res = await client.get("/api/v1/taller/repuestos?incluir_inactivos=true", headers=headers)
    assert res.status_code == 200, res.text
    res = await client.post("/api/v1/taller/repuestos", headers=headers,
        json={"codigo": "ROL-TEST", "nombre": "Artículo"})
    assert res.status_code == (201 if rol == "ADMIN" else 403), res.text
    ot, falla, repuesto, ruta = contexto_repuestos
    res = await client.post(ruta, headers=headers, json=alta(repuesto["id"]))
    assert res.status_code == (201 if rol == "ADMIN" else 403), res.text


async def test_usuario_inactivo_no_puede_registrar(client, contexto_repuestos):
    from app.core.security import create_access_token
    headers = {"Authorization": f"Bearer {create_access_token(subject=5)}"}
    res = await client.post(contexto_repuestos[3], headers=headers, json=alta(contexto_repuestos[2]["id"]))
    assert res.status_code == 401, res.text
