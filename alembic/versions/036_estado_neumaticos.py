"""Estado de los reportes de neumáticos."""
from alembic import op
import sqlalchemy as sa

revision = "036_estado_neumaticos"
down_revision = "035_comentarios_neumaticos"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reportes_neumaticos", sa.Column("estado", sa.String(20), nullable=False, server_default="REGISTRADO"))
    op.create_check_constraint("ck_neumaticos_estado", "reportes_neumaticos", "estado IN ('REGISTRADO', 'INFORMADO')")


def downgrade():
    op.drop_constraint("ck_neumaticos_estado", "reportes_neumaticos", type_="check")
    op.drop_column("reportes_neumaticos", "estado")
