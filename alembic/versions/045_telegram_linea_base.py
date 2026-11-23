"""Permitir registrar alertas existentes sin enviarlas."""
from alembic import op

revision = "045_telegram_linea_base"
down_revision = "044_telegram_envios"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("telegram_envios") as batch:
        batch.drop_constraint("ck_telegram_envios_estado", type_="check")
        batch.create_check_constraint("ck_telegram_envios_estado", "estado IN ('PENDIENTE','ENVIANDO','ACEPTADO','FALLIDO','INCIERTO','REINTENTABLE','OMITIDO')")


def downgrade():
    raise RuntimeError("La línea base de Telegram no se puede revertir sin revisar sus registros")
