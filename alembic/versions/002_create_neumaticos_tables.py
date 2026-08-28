"""Create reportes_neumaticos table with foreign keys to usuarios

Revision ID: 002_neumaticos
Revises: 001_usuarios
Create Date: 2026-08-25 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_neumaticos'
down_revision: Union[str, None] = '001_usuarios'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'reportes_neumaticos' not in tables:
        op.create_table(
            'reportes_neumaticos',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('n_bus', sa.String(length=50), nullable=True),
            sa.Column('tipo_bus', sa.String(length=50), nullable=True),
            sa.Column('ruedas', sa.JSON(), nullable=True),
            sa.Column('motivo', sa.Text(), nullable=True),
            sa.Column('precio', sa.Numeric(precision=12, scale=2), nullable=True),
            sa.Column('marca_fuego', sa.String(length=100), nullable=True),
            sa.Column('evidencia_url', sa.String(length=500), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('fecha_subida', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_reportes_neumaticos_id'), 'reportes_neumaticos', ['id'], unique=False)
        op.create_index(op.f('ix_reportes_neumaticos_usuario_id'), 'reportes_neumaticos', ['usuario_id'], unique=False)
        op.create_index(op.f('ix_reportes_neumaticos_n_bus'), 'reportes_neumaticos', ['n_bus'], unique=False)


def downgrade() -> None:
    op.drop_table('reportes_neumaticos')
