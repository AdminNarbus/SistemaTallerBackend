"""unificar mantenciones y desarrollo

Revision ID: d527b38486e0
Revises: ('038_control_mantenciones', '041_revision_fallas')
Create Date: 2026-11-17 10:52:01.335671

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd527b38486e0'
down_revision: Union[str, None] = ('038_control_mantenciones', '041_revision_fallas')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
