"""Preservar originales antes de consolidar OTs."""
from alembic import op
import sqlalchemy as sa

revision = '020a_archivo_consolidacion'
down_revision = '020_trazabilidad_fallas'
branch_labels = None
depends_on = None
TABLES = ('taller_solicitud_detalles','taller_solicitud_comentarios','taller_solicitud_mecanicos',
          'taller_asignacion_fallas','taller_solicitud_pauta','taller_solicitud_evidencias','taller_solicitud_estadias')


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.create_table('taller_consolidacion_archivos',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('tabla',sa.String(80),nullable=False),
        sa.Column('registro_id',sa.Integer(),nullable=False),
        sa.Column('solicitud_original_id',sa.Integer(),nullable=False),
        sa.Column('solicitud_destino_id',sa.Integer(),nullable=False),
        sa.Column('datos_originales',sa.JSON(),nullable=False),
        sa.Column('fecha_archivo',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint('tabla','registro_id',name='uq_consolidacion_original'))
    op.execute('''CREATE TEMP TABLE archivo_ot_map ON COMMIT DROP AS
        WITH activas AS (
            SELECT s.id,first_value(s.id) OVER (
                PARTITION BY COALESCE('B:' || COALESCE(s.bus_id,b.id)::text,'N:' || lower(trim(s.n_bus)))
                ORDER BY s.fecha_creacion,s.id) destino_id,
                count(*) OVER (PARTITION BY COALESCE('B:' || COALESCE(s.bus_id,b.id)::text,'N:' || lower(trim(s.n_bus)))) cantidad
            FROM taller_solicitudes s LEFT JOIN buses b
              ON s.bus_id IS NULL AND lower(trim(s.n_bus))=lower(trim(b.n_bus))
            WHERE s.estado <> 'FINALIZADO')
        SELECT id,destino_id FROM activas WHERE cantidad>1''')
    op.execute('''INSERT INTO taller_consolidacion_archivos
        (tabla,registro_id,solicitud_original_id,solicitud_destino_id,datos_originales)
        SELECT 'taller_solicitudes',s.id,s.id,m.destino_id,row_to_json(s)
        FROM taller_solicitudes s JOIN archivo_ot_map m ON m.id=s.id''')
    for table in TABLES:
        op.execute(sa.text(f'''INSERT INTO taller_consolidacion_archivos
            (tabla,registro_id,solicitud_original_id,solicitud_destino_id,datos_originales)
            SELECT :tabla,r.id,r.solicitud_id,m.destino_id,row_to_json(r)
            FROM {table} r JOIN archivo_ot_map m ON m.id=r.solicitud_id''').bindparams(tabla=table))


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM taller_consolidacion_archivos')):
        raise RuntimeError('Preservar el archivo antes de revertir 020a; no se borran originales')
    op.drop_table('taller_consolidacion_archivos')
