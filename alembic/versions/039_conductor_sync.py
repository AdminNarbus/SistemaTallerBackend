"""Registro mensual de sincronización de conductores."""
from alembic import op
import sqlalchemy as sa

revision = "039_conductor_sync"
down_revision = "038_repuestos_por_falla"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conductor_sync",
        sa.Column("periodo", sa.String(7), primary_key=True, nullable=False),
        sa.Column("resultado", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("conductor_sync")
