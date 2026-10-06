"""Vincular evidencias fotográficas con eventos de bitácora.

Revision ID: 019_comentario_adjuntos
Revises: 018_estado_falla_detalles
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019_comentario_adjuntos"
down_revision: Union[str, None] = "018_estado_falla_detalles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("taller_solicitud_evidencias")}
    if "comentario_id" not in columns:
        op.add_column(
            "taller_solicitud_evidencias",
            sa.Column("comentario_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_taller_solicitud_evidencias_comentario_id",
            "taller_solicitud_evidencias",
            "taller_solicitud_comentarios",
            ["comentario_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(
            "ix_taller_solicitud_evidencias_comentario_id",
            "taller_solicitud_evidencias",
            ["comentario_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("taller_solicitud_evidencias")}
    if "comentario_id" in columns:
        op.drop_index("ix_taller_solicitud_evidencias_comentario_id", table_name="taller_solicitud_evidencias")
        op.drop_constraint("fk_taller_solicitud_evidencias_comentario_id", "taller_solicitud_evidencias", type_="foreignkey")
        op.drop_column("taller_solicitud_evidencias", "comentario_id")
