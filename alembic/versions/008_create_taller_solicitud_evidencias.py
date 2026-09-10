"""Crear tabla taller_solicitud_evidencias para soporte de múltiples evidencias (3NF)

Revision ID: 008_solicitud_evidencias
Revises: 007_conductores
Create Date: 2026-09-10 10:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '008_solicitud_evidencias'
down_revision: Union[str, None] = '007_conductores'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Crear tabla taller_solicitud_evidencias si no existe
    if 'taller_solicitud_evidencias' not in tables:
        op.create_table(
            'taller_solicitud_evidencias',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('solicitud_id', sa.Integer(), nullable=False),
            sa.Column('detalle_id', sa.Integer(), nullable=True),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('url', sa.Text(), nullable=False),
            sa.Column('original_filename', sa.String(length=255), nullable=True),
            sa.Column('size_bytes', sa.Integer(), nullable=True),
            sa.Column('content_type', sa.String(length=100), nullable=True),
            sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['solicitud_id'], ['taller_solicitudes.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['detalle_id'], ['taller_solicitud_detalles.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_taller_solicitud_evidencias_id'), 'taller_solicitud_evidencias', ['id'], unique=False)
        op.create_index(op.f('ix_taller_solicitud_evidencias_solicitud_id'), 'taller_solicitud_evidencias', ['solicitud_id'], unique=False)
        op.create_index(op.f('ix_taller_solicitud_evidencias_detalle_id'), 'taller_solicitud_evidencias', ['detalle_id'], unique=False)
        op.create_index(op.f('ix_taller_solicitud_evidencias_usuario_id'), 'taller_solicitud_evidencias', ['usuario_id'], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'taller_solicitud_evidencias' in tables:
        op.drop_table('taller_solicitud_evidencias')
