"""Agregar estado de cola para reportes de conductores."""
from alembic import op
import sqlalchemy as sa

revision = "043_whatsapp_solicitudes"
down_revision = "042_whatsapp_envios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("whatsapp_envios") as batch:
        batch.drop_constraint("ck_whatsapp_envios_estado", type_="check")
        batch.create_check_constraint("ck_whatsapp_envios_estado", "estado IN ('PENDIENTE','ENVIANDO','ACEPTADO','FALLIDO','INCIERTO','REINTENTABLE')")


def downgrade() -> None:
    # No se descartan avisos pendientes al revertir la migración.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM whatsapp_envios WHERE estado = 'PENDIENTE'")).scalar():
        raise RuntimeError("Existen avisos pendientes de solicitudes; procesarlos antes de revertir")
    with op.batch_alter_table("whatsapp_envios") as batch:
        batch.drop_constraint("ck_whatsapp_envios_estado", type_="check")
        batch.create_check_constraint("ck_whatsapp_envios_estado", "estado IN ('ENVIANDO','ACEPTADO','FALLIDO','INCIERTO','REINTENTABLE')")
