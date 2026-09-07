"""Create base tables: roles, usuarios

Revision ID: 001_usuarios
Revises: 
Create Date: 2026-08-25 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_usuarios'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Tabla roles
    if 'roles' not in tables:
        op.create_table(
            'roles',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('nombre', sa.String(length=50), nullable=False),
            sa.Column('descripcion', sa.String(length=255), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nombre')
        )
        op.create_index(op.f('ix_roles_id'), 'roles', ['id'], unique=False)
        op.create_index(op.f('ix_roles_nombre'), 'roles', ['nombre'], unique=True)

    # 2. Tabla usuarios
    if 'usuarios' not in tables:
        op.create_table(
            'usuarios',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('nombre', sa.String(length=100), nullable=True),
            sa.Column('apellido', sa.String(length=100), nullable=True),
            sa.Column('username', sa.String(length=100), nullable=False),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('rol_id', sa.Integer(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['rol_id'], ['roles.id'], ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_usuarios_id'), 'usuarios', ['id'], unique=False)
        op.create_index(op.f('ix_usuarios_username'), 'usuarios', ['username'], unique=True)


def downgrade() -> None:
    op.drop_table('usuarios')
    op.drop_table('roles')
