import pytest
from sqlalchemy import func, select

from app.modules.taller.models.taller_solicitud_estado_evento import TallerSolicitudEstadoEvento
from app.modules.taller.services.trazabilidad_estados import RegistroEstadoOT, registrar_evento_estado


async def crear_ot(client, headers, n_bus='HIST-001', detalles=None):
    res = await client.post('/api/v1/taller/solicitudes', headers=headers,
                            json={'n_bus': n_bus, 'detalles': detalles or []})
    assert res.status_code == 201, res.text
    return res.json()


@pytest.mark.asyncio
async def test_historial_conserva_cierres_reapertura_y_paginacion(
    client, db_session, auth_headers_conductor, auth_headers_supervisor,
):
    ot = await crear_ot(client, auth_headers_conductor)
    url = f"/api/v1/taller/{ot['id']}"
    cierres = []
    for estado in ('FINALIZADO', 'PENDIENTE', 'FINALIZADO'):
        res = await client.patch(url + '/estado', headers=auth_headers_supervisor,
                                 json={'estado': estado, 'comentario': 'Cambio operativo'})
        assert res.status_code == 200, res.text
        if estado == 'FINALIZADO':
            cierres.append(res.json()['fecha_cierre'])
        else:
            assert res.json()['fecha_cierre'] is None
    historial = await client.get(url + '/historial-estados', headers=auth_headers_conductor)
    assert historial.status_code == 200
    eventos = historial.json()
    assert [e['estado_nuevo'] for e in eventos] == ['PENDIENTE', 'FINALIZADO', 'PENDIENTE', 'FINALIZADO']
    assert [e['estado_anterior'] for e in eventos] == [None, 'PENDIENTE', 'FINALIZADO', 'PENDIENTE']
    assert [e['fecha_evento'] for e in eventos if e['estado_nuevo'] == 'FINALIZADO'] == cierres
    assert all(e['usuario_actor_id'] == 4 and e['comentario_id'] for e in eventos[1:])
    assert historial.headers['X-Total-Count'] == '4'
    pagina = await client.get(url + '/historial-estados?skip=1&limit=2', headers=auth_headers_conductor)
    assert pagina.json() == eventos[1:3]
    assert pagina.headers['X-Total-Count'] == '4'
    repetido = await client.patch(url + '/estado', headers=auth_headers_supervisor, json={'estado': 'FINALIZADO'})
    assert repetido.status_code == 422
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitudEstadoEvento)) == 4
    assert (await client.get(url + '/historial-estados')).status_code == 401
    assert (await client.get('/api/v1/taller/99999/historial-estados', headers=auth_headers_conductor)).status_code == 404
    assert (await client.get(url + '/historial-estados?limit=0', headers=auth_headers_conductor)).status_code == 422


@pytest.mark.asyncio
async def test_transiciones_cuadrilla_cierre_batch_y_anexar_fallas(
    client, auth_headers_conductor, auth_headers_mecanico1, auth_headers_supervisor,
):
    ot = await crear_ot(client, auth_headers_conductor, detalles=[{'falla_id': 1}])
    url = f"/api/v1/taller/{ot['id']}"
    for route, payload in [('/tomar', {}), ('/liberar-turno', {}), ('/tomar', {}), ('/finalizar', {})]:
        res = await client.post(url + route, headers=auth_headers_mecanico1, json=payload)
        assert res.status_code == 200, res.text
    historial = (await client.get(url + '/historial-estados', headers=auth_headers_supervisor)).json()
    assert [e['estado_nuevo'] for e in historial] == ['PENDIENTE', 'EN_REPARACION', 'PENDIENTE', 'EN_REPARACION', 'LIBERADO']
    assert historial[-1]['comentario_id'] is not None
    # Una segunda llamada que conserva LIBERADO no agrega una transición.
    assert (await client.post(url + '/finalizar', headers=auth_headers_mecanico1, json={})).status_code == 200
    anexada = await crear_ot(client, auth_headers_conductor, detalles=[{'falla_id': 2}])
    assert anexada['id'] == ot['id']
    actual = (await client.get(url + '/historial-estados', headers=auth_headers_supervisor)).json()
    assert actual == historial
    # Resolver fallas y volver a cerrar utiliza el camino de UPDATE masivo.
    for detalle in anexada['detalles']:
        res = await client.patch(url + f"/detalles/{detalle['id']}/check", headers=auth_headers_mecanico1,
                                 json={'estado': 'RESUELTA'})
        assert res.status_code == 200, res.text
    res = await client.post(url + '/finalizar', headers=auth_headers_mecanico1, json={})
    assert res.status_code == 200, res.text
    actual = (await client.get(url + '/historial-estados', headers=auth_headers_supervisor)).json()
    assert actual[-1]['estado_anterior'] == 'LIBERADO'
    assert actual[-1]['estado_nuevo'] == 'FINALIZADO'


@pytest.mark.asyncio
async def test_evento_sin_cambio_y_rollback(db_session, seed_test_data):
    from datetime import datetime, timezone
    from app.modules.taller.models.taller_solicitud import TallerSolicitud
    ot = TallerSolicitud(n_bus='HIST-ROLLBACK', estado='PENDIENTE')
    db_session.add(ot)
    await db_session.commit()
    id_ot = ot.id
    args = dict(solicitud_id=id_ot, estado_anterior='PENDIENTE', actor_id=2,
                actor_nombre='Pedro', fecha_evento=datetime.now(timezone.utc))
    assert await registrar_evento_estado(db_session, RegistroEstadoOT(estado_nuevo='PENDIENTE', **args)) is None
    ot.estado = 'FINALIZADO'
    await registrar_evento_estado(db_session, RegistroEstadoOT(estado_nuevo='FINALIZADO', **args))
    await db_session.flush()
    await db_session.rollback()
    assert await db_session.scalar(select(func.count()).select_from(TallerSolicitudEstadoEvento)) == 0
    assert await db_session.scalar(select(TallerSolicitud.estado).where(TallerSolicitud.id == id_ot)) == 'PENDIENTE'
