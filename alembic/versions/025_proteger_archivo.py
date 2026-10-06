"""Instalar archivo en bases ya actualizadas y proteger los originales."""
from alembic import op
import sqlalchemy as sa

revision = '025_proteger_archivo'
down_revision = '024_historial_estados_ot'
branch_labels = None
depends_on = None


def upgrade():
    if not sa.inspect(op.get_bind()).has_table('taller_consolidacion_archivos'):
        op.create_table('taller_consolidacion_archivos',
            sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('tabla',sa.String(80),nullable=False),
            sa.Column('registro_id',sa.Integer(),nullable=False),
            sa.Column('solicitud_original_id',sa.Integer(),nullable=False),
            sa.Column('solicitud_destino_id',sa.Integer(),nullable=False),
            sa.Column('datos_originales',sa.JSON(),nullable=False),
            sa.Column('fecha_archivo',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
            sa.UniqueConstraint('tabla','registro_id',name='uq_consolidacion_original'))
    op.execute('''CREATE TRIGGER tr_archivo_consolidacion_inmutable
        BEFORE UPDATE OR DELETE ON taller_consolidacion_archivos
        FOR EACH ROW EXECUTE FUNCTION narbus_proteger_historial()''')
    op.execute('''CREATE TRIGGER tr_archivo_consolidacion_no_truncate
        BEFORE TRUNCATE ON taller_consolidacion_archivos
        FOR EACH STATEMENT EXECUTE FUNCTION narbus_proteger_historial()''')


def downgrade():
    op.execute('DROP TRIGGER tr_archivo_consolidacion_no_truncate ON taller_consolidacion_archivos')
    op.execute('DROP TRIGGER tr_archivo_consolidacion_inmutable ON taller_consolidacion_archivos')
