"""Separar fecha efectiva y fecha de registro en las bitácoras."""
from alembic import op
import sqlalchemy as sa

revision = "027_fechas_evento_registro"
down_revision = "026_fecha_cambio_estado_detalle"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "taller_solicitud_comentarios",
        sa.Column("fecha_evento", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "taller_falla_eventos",
        sa.Column(
            "fecha_registro",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    op.drop_column("taller_falla_eventos", "fecha_registro")
    op.drop_column("taller_solicitud_comentarios", "fecha_evento")
