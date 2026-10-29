"""Conservar motivos descriptivos completos al egresar del taller.

Revision ID: 032_motivo_salida_estadia
Revises: 031_depuracion_supervision
"""
from alembic import op
import sqlalchemy as sa


revision = "032_motivo_salida_estadia"
down_revision = "031_depuracion_supervision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("taller_solicitud_estadias") as batch_op:
        batch_op.alter_column(
            "motivo_salida",
            existing_type=sa.String(50),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    # PostgreSQL rechaza la reducción si existen motivos de más de 50 caracteres;
    # no usar un cast explícito que truncaría silenciosamente la trazabilidad.
    with op.batch_alter_table("taller_solicitud_estadias") as batch_op:
        batch_op.alter_column(
            "motivo_salida",
            existing_type=sa.Text(),
            type_=sa.String(50),
            existing_nullable=True,
        )
