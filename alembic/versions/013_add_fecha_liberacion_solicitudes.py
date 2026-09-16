"""Agregar columna fecha_liberacion a taller_solicitudes

Revision ID: 013_add_fecha_liberacion
Revises: 012_refactor_estados_liberado
Create Date: 2026-09-16 15:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '013_add_fecha_liberacion'
down_revision: Union[str, None] = '012_refactor_estados_liberado'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('taller_solicitudes')]

    if 'fecha_liberacion' not in columns:
        op.add_column(
            'taller_solicitudes',
            sa.Column('fecha_liberacion', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            'ix_taller_solicitudes_fecha_liberacion',
            'taller_solicitudes',
            ['fecha_liberacion'],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('taller_solicitudes')]

    if 'fecha_liberacion' in columns:
        op.drop_index('ix_taller_solicitudes_fecha_liberacion', table_name='taller_solicitudes')
        op.drop_column('taller_solicitudes', 'fecha_liberacion')
