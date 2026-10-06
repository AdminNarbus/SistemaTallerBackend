"""Unificar estadías abiertas de distintas OTs consolidadas, sin inferir salidas."""
from alembic import op
import sqlalchemy as sa

revision = '021b_estadias_consolidadas'
down_revision = '021a_saneamiento_historial'
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table('taller_consolidacion_archivos'):
        return
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute('''WITH candidatos AS (
        SELECT e.solicitud_id FROM taller_solicitud_estadias e
        JOIN taller_consolidacion_archivos a
          ON a.tabla='taller_solicitud_estadias' AND a.registro_id=e.id
         AND a.solicitud_destino_id=e.solicitud_id
         AND a.datos_originales->>'fecha_salida' IS NULL
        WHERE e.fecha_salida IS NULL GROUP BY e.solicitud_id
        HAVING count(*)>1 AND count(*)=count(DISTINCT a.solicitud_original_id)
           AND count(*)=(SELECT count(*) FROM taller_solicitud_estadias x
                         WHERE x.solicitud_id=e.solicitud_id AND x.fecha_salida IS NULL)
    ), ordenadas AS (
        SELECT e.id,row_number() OVER (PARTITION BY e.solicitud_id ORDER BY e.fecha_ingreso,e.id) orden
        FROM taller_solicitud_estadias e JOIN candidatos c ON c.solicitud_id=e.solicitud_id
        WHERE e.fecha_salida IS NULL)
    DELETE FROM taller_solicitud_estadias e USING ordenadas o WHERE e.id=o.id AND o.orden>1''')


def downgrade():
    if not sa.inspect(op.get_bind()).has_table('taller_consolidacion_archivos'):
        return
    op.execute('''INSERT INTO taller_solicitud_estadias
        (id,solicitud_id,numero_visita,fecha_ingreso,fecha_salida,horas_estadia,motivo_salida)
        SELECT a.registro_id,a.solicitud_destino_id,
            (SELECT COALESCE(max(numero_visita),0) FROM taller_solicitud_estadias e
             WHERE e.solicitud_id=a.solicitud_destino_id)
             + row_number() OVER (PARTITION BY a.solicitud_destino_id ORDER BY a.registro_id),
            (a.datos_originales->>'fecha_ingreso')::timestamptz,NULL,NULL,
            a.datos_originales->>'motivo_salida'
        FROM taller_consolidacion_archivos a
        WHERE a.tabla='taller_solicitud_estadias' AND a.datos_originales->>'fecha_salida' IS NULL
          AND NOT EXISTS (SELECT 1 FROM taller_solicitud_estadias e WHERE e.id=a.registro_id)''')
