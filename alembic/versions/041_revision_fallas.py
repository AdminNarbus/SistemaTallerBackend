"""Revisión individual de fallas sin reinterpretar el historial de las OT."""
from alembic import op
import sqlalchemy as sa

revision = "041_revision_fallas"
down_revision = "040_rol_visual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("taller_solicitud_detalles", sa.Column("estado_revision", sa.String(20), nullable=False, server_default="PENDIENTE"))
    op.add_column("taller_solicitud_detalles", sa.Column("revisado_por_id", sa.Integer(), nullable=True))
    op.add_column("taller_solicitud_detalles", sa.Column("fecha_revision", sa.DateTime(timezone=True), nullable=True))
    # Las fallas previas de OT aceptadas conservan su condición operativa.
    # No se inventan autores ni fechas de aprobación históricos.
    op.execute(sa.text("""UPDATE taller_solicitud_detalles SET estado_revision = 'APROBADA'
        WHERE solicitud_id IN (SELECT id FROM taller_solicitudes WHERE es_ot = true)"""))
    with op.batch_alter_table("taller_solicitud_detalles") as batch:
        batch.create_foreign_key("fk_detalles_revisado_por_usuarios", "usuarios", ["revisado_por_id"], ["id"], ondelete="RESTRICT")
        batch.create_check_constraint("ck_detalles_estado_revision", "estado_revision IN ('PENDIENTE','APROBADA')")
        batch.create_index("ix_detalles_solicitud_revision", ["solicitud_id", "estado_revision"])
        batch.create_index("ix_taller_solicitud_detalles_revisado_por_id", ["revisado_por_id"])


def downgrade() -> None:
    with op.batch_alter_table("taller_solicitud_detalles") as batch:
        batch.drop_index("ix_taller_solicitud_detalles_revisado_por_id")
        batch.drop_index("ix_detalles_solicitud_revision")
        batch.drop_constraint("ck_detalles_estado_revision", type_="check")
        batch.drop_constraint("fk_detalles_revisado_por_usuarios", type_="foreignkey")
        batch.drop_column("fecha_revision")
        batch.drop_column("revisado_por_id")
        batch.drop_column("estado_revision")
