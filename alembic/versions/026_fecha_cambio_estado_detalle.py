"""Persistir fecha del último cambio de estado de una avería."""
from alembic import op
import sqlalchemy as sa

revision = "026_fecha_cambio_estado_detalle"
down_revision = "025_proteger_archivo"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "taller_solicitud_detalles",
        sa.Column("fecha_cambio_estado", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("taller_solicitud_detalles", "fecha_cambio_estado")
