"""Corregir datos históricos confirmados antes de instalar restricciones.

Revision ID: 021a_saneamiento_historial
Revises: 021_consolidar_ots_activas

Dates confirmed by the operator, expressed in America/Santiago (-03:00).
Record IDs alone never authorize a correction: original timestamps/payload must match.
"""
from alembic import op
from datetime import datetime
import sqlalchemy as sa

revision = '021a_saneamiento_historial'
down_revision = '021_consolidar_ots_activas'
branch_labels = None
depends_on = None

SALIDAS_CONFIRMADAS = [
    (1, 1, '2026-09-29 11:19:22.069005-03:00', '2026-09-29 13:00:00-03:00'),
    (3, 3, '2026-10-02 09:34:46.239249-03:00', '2026-10-02 14:00:00-03:00'),
    (4, 4, '2026-10-02 10:52:20.615275-03:00', '2026-10-02 15:00:00-03:00'),
]
RUEDAS_ORIGINALES = '[{"posicion":"1D","estado":"Bueno","presion":110},{"posicion":"1I","estado":"Regular","presion":105}]'


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column('reportes_neumaticos', sa.Column('ruedas_originales', sa.JSON(), nullable=True))
    op.add_column('reportes_neumaticos', sa.Column('reporte_origen_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_neumaticos_reporte_origen', 'reportes_neumaticos', 'reportes_neumaticos', ['reporte_origen_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_reportes_neumaticos_reporte_origen_id', 'reportes_neumaticos', ['reporte_origen_id'])
    connection = op.get_bind()
    for record, visit, ingreso, salida in SALIDAS_CONFIRMADAS:
        connection.execute(sa.text('''UPDATE taller_solicitud_estadias
            SET fecha_salida=CAST(:salida AS timestamptz), motivo_salida='CORRECCION_HISTORICA_CONFIRMADA',
                horas_estadia=round((extract(epoch FROM (CAST(:salida AS timestamptz)-fecha_ingreso))/3600)::numeric,1)
            WHERE id=:id AND solicitud_id=3 AND numero_visita=:visita
                AND fecha_ingreso=CAST(:ingreso AS timestamptz) AND fecha_salida IS NULL'''),
            {'id': record, 'visita': visit, 'ingreso': datetime.fromisoformat(ingreso), 'salida': datetime.fromisoformat(salida)})
    # Preserve the complete legacy payload; the fire mark belongs only to 1D.
    connection.execute(sa.text('''INSERT INTO reportes_neumaticos
        (usuario_id,bus_id,n_bus,tipo_bus,ruedas,motivo,marca_fuego,evidencia_url,fecha_subida,created_at,updated_at,reporte_origen_id)
        SELECT usuario_id,bus_id,n_bus,tipo_bus,json_build_array(ruedas->1),motivo,NULL,evidencia_url,fecha_subida,created_at,updated_at,id
        FROM reportes_neumaticos WHERE id=1 AND ruedas::jsonb=CAST(:original AS jsonb)
            AND marca_fuego='MF-301-A' '''), {'original': RUEDAS_ORIGINALES})
    connection.execute(sa.text('''UPDATE reportes_neumaticos SET ruedas_originales=ruedas,ruedas=json_build_array(ruedas->0)
        WHERE id=1 AND ruedas::jsonb=CAST(:original AS jsonb) AND marca_fuego='MF-301-A' '''), {'original': RUEDAS_ORIGINALES})
    # A single scalar or object represents exactly one tyre; normalization loses no information.
    op.execute('''UPDATE reportes_neumaticos SET ruedas_originales=ruedas, ruedas=json_build_array(ruedas)
        WHERE jsonb_typeof(ruedas::jsonb) IN ('string','number','object')''')


def downgrade():
    # Restore only rows still matching this migration's confirmed correction.
    connection = op.get_bind()
    for record, visit, ingreso, salida in SALIDAS_CONFIRMADAS:
        connection.execute(sa.text('''UPDATE taller_solicitud_estadias SET fecha_salida=NULL,horas_estadia=NULL,motivo_salida=NULL
            WHERE id=:id AND solicitud_id=3 AND numero_visita=:visita
                AND fecha_ingreso=CAST(:ingreso AS timestamptz) AND fecha_salida=CAST(:salida AS timestamptz)
                AND motivo_salida='CORRECCION_HISTORICA_CONFIRMADA' '''),
            {'id': record, 'visita': visit, 'ingreso': datetime.fromisoformat(ingreso), 'salida': datetime.fromisoformat(salida)})
    connection.execute(sa.text('''DELETE FROM reportes_neumaticos WHERE reporte_origen_id=1 AND marca_fuego IS NULL
        AND ruedas::jsonb=CAST(:rueda AS jsonb)'''), {'rueda': '[{"posicion":"1I","estado":"Regular","presion":105}]'})
    op.execute('UPDATE reportes_neumaticos SET ruedas=ruedas_originales WHERE ruedas_originales IS NOT NULL')
    op.drop_index('ix_reportes_neumaticos_reporte_origen_id', table_name='reportes_neumaticos')
    op.drop_constraint('fk_neumaticos_reporte_origen', 'reportes_neumaticos', type_='foreignkey')
    op.drop_column('reportes_neumaticos', 'reporte_origen_id')
    op.drop_column('reportes_neumaticos', 'ruedas_originales')
