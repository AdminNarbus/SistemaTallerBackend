"""Refactorizar estados de taller_solicitudes: migrar PENDIENTE_REASIGNACION a PENDIENTE

Revision ID: 012_refactor_estados_liberado
Revises: 011_add_buses_audit_fields
Create Date: 2026-09-16 09:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '012_refactor_estados_liberado'
down_revision: Union[str, None] = '011_add_buses_audit_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Migrar solicitudes en PENDIENTE_REASIGNACION al estado canonico PENDIENTE
    if 'taller_solicitudes' in tables:
        conn.execute(sa.text("""
            UPDATE taller_solicitudes 
            SET estado = 'PENDIENTE' 
            WHERE estado = 'PENDIENTE_REASIGNACION';
        """))


def downgrade() -> None:
    # No es necesario revertir PENDIENTE a PENDIENTE_REASIGNACION dado que
    # PENDIENTE es un estado canónico universalmente compatible.
    pass
