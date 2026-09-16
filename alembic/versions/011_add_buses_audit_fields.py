"""Agregar campos de auditoria y trazabilidad temporal a tabla buses

Revision ID: 011_add_buses_audit_fields
Revises: 010_add_index_usuarios_rol_id
Create Date: 2026-09-15 17:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '011_add_buses_audit_fields'
down_revision: Union[str, None] = '010_add_index_usuarios_rol_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns_buses = [c['name'] for c in inspector.get_columns('buses')]
    indexes_buses = [idx['name'] for idx in inspector.get_indexes('buses')]

    # 1. fecha_creacion
    if 'fecha_creacion' not in columns_buses:
        op.add_column(
            'buses',
            sa.Column(
                'fecha_creacion',
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # 2. fecha_baja
    if 'fecha_baja' not in columns_buses:
        op.add_column(
            'buses',
            sa.Column('fecha_baja', sa.DateTime(timezone=True), nullable=True),
        )

    # 3. motivo_baja
    if 'motivo_baja' not in columns_buses:
        op.add_column(
            'buses',
            sa.Column('motivo_baja', sa.Text(), nullable=True),
        )

    # 4. usuario_baja_id
    if 'usuario_baja_id' not in columns_buses:
        op.add_column(
            'buses',
            sa.Column(
                'usuario_baja_id',
                sa.Integer(),
                sa.ForeignKey('usuarios.id', ondelete='SET NULL'),
                nullable=True,
            ),
        )

    # 5. Indice en usuario_baja_id
    if 'ix_buses_usuario_baja_id' not in indexes_buses:
        op.create_index(
            'ix_buses_usuario_baja_id',
            'buses',
            ['usuario_baja_id'],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns_buses = [c['name'] for c in inspector.get_columns('buses')]
    indexes_buses = [idx['name'] for idx in inspector.get_indexes('buses')]

    if 'ix_buses_usuario_baja_id' in indexes_buses:
        op.drop_index('ix_buses_usuario_baja_id', table_name='buses')

    if 'usuario_baja_id' in columns_buses:
        op.drop_column('buses', 'usuario_baja_id')

    if 'motivo_baja' in columns_buses:
        op.drop_column('buses', 'motivo_baja')

    if 'fecha_baja' in columns_buses:
        op.drop_column('buses', 'fecha_baja')

    if 'fecha_creacion' in columns_buses:
        op.drop_column('buses', 'fecha_creacion')
