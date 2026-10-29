"""Distinguir solicitudes y OT sin alterar su historial previo.

Revision ID: 033_es_ot
Revises: 032_motivo_salida_estadia
"""
from alembic import op
import sqlalchemy as sa

revision = "033_es_ot"
down_revision = "032_motivo_salida_estadia"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Los registros anteriores ya eran tratados como OT. El default temporal
    # conserva esa clasificación; los reportes posteriores nacen como solicitud.
    op.add_column("taller_solicitudes", sa.Column("es_ot", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("taller_solicitudes") as batch_op:
        batch_op.alter_column("es_ot", existing_type=sa.Boolean(), existing_nullable=False, server_default=sa.false())


def downgrade() -> None:
    op.drop_column("taller_solicitudes", "es_ot")
