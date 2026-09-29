"""Add optional phone to users.

Revision ID: 016_add_telefono_usuarios
Revises: 015_update_pauta_items_10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016_add_telefono_usuarios"
down_revision: Union[str, None] = "015_update_pauta_items_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "telefono" not in {column["name"] for column in inspector.get_columns("usuarios")}:
        op.add_column("usuarios", sa.Column("telefono", sa.String(length=30), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "telefono" in {column["name"] for column in inspector.get_columns("usuarios")}:
        op.drop_column("usuarios", "telefono")
