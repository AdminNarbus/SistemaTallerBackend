"""Agregar restriccion unica a taller_solicitud_pauta (solicitud_id, item_id)

Revision ID: 009_unique_solicitud_pauta
Revises: 008_solicitud_evidencias
Create Date: 2026-09-11 10:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009_unique_solicitud_pauta'
down_revision: Union[str, None] = '008_solicitud_evidencias'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    constraints = [c['name'] for c in inspector.get_unique_constraints('taller_solicitud_pauta')]

    # Asegurar restriccion unica uq_solicitud_pauta_item para soportar ON CONFLICT DO UPDATE
    if 'uq_solicitud_pauta_item' not in constraints:
        op.create_unique_constraint(
            'uq_solicitud_pauta_item',
            'taller_solicitud_pauta',
            ['solicitud_id', 'item_id']
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    constraints = [c['name'] for c in inspector.get_unique_constraints('taller_solicitud_pauta')]

    if 'uq_solicitud_pauta_item' in constraints:
        op.drop_constraint('uq_solicitud_pauta_item', 'taller_solicitud_pauta', type_='unique')
