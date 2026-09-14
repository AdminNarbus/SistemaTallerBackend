"""Agregar indice ix_usuarios_rol_id a tabla usuarios

Revision ID: 010_add_index_usuarios_rol_id
Revises: 009_unique_solicitud_pauta
Create Date: 2026-09-14 11:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '010_add_index_usuarios_rol_id'
down_revision: Union[str, None] = '009_unique_solicitud_pauta'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    indexes = [idx['name'] for idx in inspector.get_indexes('usuarios')]

    # Si existía con nomenclatura no canónica 'idx_usuarios_rol_id', normalizar al estándar 'ix_usuarios_rol_id'
    if 'idx_usuarios_rol_id' in indexes:
        op.drop_index('idx_usuarios_rol_id', table_name='usuarios')

    # Crear índice en rol_id para optimizar filtros y JOINs entre usuarios y roles
    if 'ix_usuarios_rol_id' not in indexes:
        op.create_index(
            'ix_usuarios_rol_id',
            'usuarios',
            ['rol_id'],
            unique=False
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    indexes = [idx['name'] for idx in inspector.get_indexes('usuarios')]

    if 'ix_usuarios_rol_id' in indexes:
        op.drop_index('ix_usuarios_rol_id', table_name='usuarios')
