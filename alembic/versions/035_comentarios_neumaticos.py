"""Comentarios de reportes de neumáticos."""
from alembic import op
import sqlalchemy as sa

revision = "035_comentarios_neumaticos"
down_revision = "034_pauta_mecanicos"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("reportes_neumaticos_comentarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reporte_id", sa.Integer(), sa.ForeignKey("reportes_neumaticos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=False),
        sa.Column("fecha_registro", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_reportes_neumaticos_comentarios_reporte_id", "reportes_neumaticos_comentarios", ["reporte_id"])


def downgrade():
    op.drop_index("ix_reportes_neumaticos_comentarios_reporte_id", table_name="reportes_neumaticos_comentarios")
    op.drop_table("reportes_neumaticos_comentarios")
