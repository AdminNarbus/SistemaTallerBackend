"""Recupera evidencia de bitácora sin alterar comentarios ni el estado de la OT.

python -m scripts.importar_historial_estados_ot [--aplicar] [--batch-size 500]
"""
import argparse
import logging
import re

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.modules.auth.models.usuario import Usuario
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_solicitud_estado_evento import TallerSolicitudEstadoEvento

logger = logging.getLogger(__name__)
ESTADOS = frozenset(('REPORTADO', 'PENDIENTE', 'EN_REPARACION', 'LIBERADO', 'FINALIZADO'))
CAMBIO = re.compile(r'Supervisora (?P<nombre>.+?) cambió el estado de (?P<anterior>[A-Z_]+) a (?P<nuevo>[A-Z_]+)\.(?: Motivo: (?P<motivo>.+))?', re.DOTALL)
CIERRE = re.compile(r'(?P<nombre>.+?) finalizó los trabajos de la OT(?: y liberó el bus para operaciones\.| \(el bus permanece en taller\)\.)(?: Comentario de cierre: .*| Motivo cierre parcial: .*| Justificación pauta preventiva: .*)?', re.DOTALL)


def interpretar_comentario(row):
    """Solo interpreta formatos conocidos; nunca deduce estados de un cierre."""
    texto = row['comentario']
    tipo = row['tipo']
    match = CAMBIO.fullmatch(texto) if tipo == 'CAMBIO_ESTADO' else None
    if match and match['anterior'] in ESTADOS and match['nuevo'] in ESTADOS and match['anterior'] != match['nuevo']:
        nombre = match['nombre']
        evento = dict(tipo_evento='CAMBIO_ESTADO', estado_anterior=match['anterior'], estado_nuevo=match['nuevo'], motivo=match['motivo'])
    elif tipo == 'CIERRE' and (match := CIERRE.fullmatch(texto)):
        nombre = match['nombre']
        evento = dict(tipo_evento='CIERRE_HISTORICO', estado_anterior=None, estado_nuevo=None, motivo=texto)
    else:
        return None
    evento.update(
        solicitud_id=row['solicitud_id'], comentario_id=row['id'],
        usuario_actor_id=row['usuario_id'],
        actor_nombre_snapshot=(nombre.strip() or row.get('usuario_nombre') or 'No registrado')[:200],
        fecha_evento=row['fecha_registro'], origen='BITACORA',
    )
    return evento


def importar(connection, *, aplicar=False, batch_size=500):
    if batch_size < 1:
        raise ValueError('batch_size debe ser positivo')
    if not inspect(connection).has_table('taller_solicitud_estado_eventos'):
        raise RuntimeError('Primero aplique la migración 024_historial_estados_ot')
    c = TallerSolicitudComentario.__table__
    e = TallerSolicitudEstadoEvento.__table__
    u = Usuario.__table__
    resultado = dict(importados=0, candidatos=0, ya_existentes=0, omitidos=0, ambiguos=0)
    ultimo_id = 0
    limite_id = connection.scalar(select(func.max(c.c.id))) or 0
    while True:
        rows = connection.execute(
            select(c, e.c.id.label('evento_existente'), u.c.nombre.label('usuario_nombre'))
            .outerjoin(e, e.c.comentario_id == c.c.id)
            .outerjoin(u, u.c.id == c.c.usuario_id)
            .where(c.c.id > ultimo_id, c.c.id <= limite_id).order_by(c.c.id).limit(batch_size)
        ).mappings().all()
        if not rows:
            break
        candidatos = []
        for row in rows:
            if row['evento_existente'] is not None:
                resultado['ya_existentes'] += 1
                continue
            evento = interpretar_comentario(row)
            if evento is None:
                resultado['omitidos'] += 1
                continue
            resultado['candidatos'] += 1
            if evento['tipo_evento'] == 'CIERRE_HISTORICO':
                resultado['ambiguos'] += 1
            candidatos.append(evento)
        if aplicar and candidatos:
            inserted = connection.execute(
                insert(e).values(candidatos).on_conflict_do_nothing(
                    constraint='uq_estado_evento_comentario'
                ).returning(e.c.id)
            ).scalars().all()
            resultado['importados'] += len(inserted)
            resultado['ya_existentes'] += len(candidatos) - len(inserted)
        ultimo_id = rows[-1]['id']
        # Cada lote aplicado es atómico y se puede reintentar tras un fallo.
        if aplicar:
            connection.commit()
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aplicar', action='store_true')
    parser.add_argument('--batch-size', type=int, default=500)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error('--batch-size debe ser positivo')
    engine = create_engine(settings.sync_database_url)
    try:
        with engine.connect() as connection:
            if not args.aplicar:
                connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            resultado = importar(connection, aplicar=args.aplicar, batch_size=args.batch_size)
            logger.info('%s: %s', 'Importación' if args.aplicar else 'Simulación', resultado)
    finally:
        engine.dispose()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
