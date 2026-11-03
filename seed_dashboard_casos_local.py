import json
from datetime import timedelta
from sqlalchemy import create_engine, MetaData, Table, select, text
from app.core.config import settings

engine = create_engine(settings.sync_database_url)
assert engine.url.host in {'127.0.0.1', 'localhost', '::1'}
assert settings.ENVIRONMENT.value == 'dev_local'
meta = MetaData()
names = ['buses','usuarios','taller_solicitudes','taller_solicitud_detalles','taller_solicitud_comentarios','taller_solicitud_estado_eventos']
t = {n:Table(n,meta,autoload_with=engine) for n in names}
s=t['taller_solicitudes']; d=t['taller_solicitud_detalles']; c=t['taller_solicitud_comentarios']; e=t['taller_solicitud_estado_eventos']; b=t['buses']
tag='SIMULACION DASHBOARD CASOS 20261102'
with engine.begin() as conn:
    actor=conn.execute(select(t['usuarios'].c.id).where(t['usuarios'].c.username=='simulacion.dashboard')).scalar_one()
    existing=conn.execute(select(s.c.id).where(s.c.descripcion_general.like(tag+'%'))).all()
    if existing:
        assert len(existing)==6, 'Carga parcial: revisar antes de continuar'
    else:
        buses=conn.execute(select(b.c.id,b.c.n_bus).where(b.c.is_active.is_(True),~select(s.c.id).where(s.c.bus_id==b.c.id).exists()).order_by(b.c.id).limit(6)).all()
        assert len(buses)==6, 'Se requieren seis buses libres de historial para esta prueba'
        now=conn.execute(select(text('now()'))).scalar_one()
        specs=[('Solicitada reciente',False,0),('Solicitada ayer',False,1),('OT abierta 10 dias',True,10),('OT abierta 15 dias',True,15),('OT abierta 35 dias',True,35),('OT abierta 45 dias',True,45)]
        for bus,(label,ot,days) in zip(buses,specs):
            approval=now-timedelta(days=days)
            created=approval-timedelta(hours=2) if ot else approval-timedelta(minutes=30)
            sid=conn.execute(s.insert().values(bus_id=bus.id,n_bus=bus.n_bus,usuario_creador_id=actor,es_ot=ot,estado='PENDIENTE',descripcion_general=tag+' - '+label,fecha_creacion=created,fecha_actualizacion=approval)).inserted_primary_key[0]
            conn.execute(d.insert().values(solicitud_id=sid,descripcion_personalizada='SIMULACION: revision de prueba - '+label,estado='PENDIENTE',resuelto=False,reportado_por_id=actor,fecha_creacion=created,fecha_reporte=created))
            conn.execute(e.insert().values(solicitud_id=sid,tipo_evento='CREACION',estado_nuevo='PENDIENTE',usuario_actor_id=actor,actor_nombre_snapshot='Simulacion Dashboard',fecha_evento=created,origen='OPERACION',motivo=tag))
            if ot:
                conn.execute(c.insert().values(solicitud_id=sid,usuario_id=actor,tipo='SISTEMA',comentario='Solicitud aprobada como OT. SIMULACION: '+label,fecha_registro=approval,fecha_evento=approval))
    result=conn.execute(select(s.c.id,s.c.n_bus,s.c.es_ot,s.c.estado,s.c.fecha_creacion,s.c.descripcion_general).where(s.c.descripcion_general.like(tag+'%')).order_by(s.c.id)).mappings().all()
    print(json.dumps([dict(r) for r in result],default=str,ensure_ascii=False))
