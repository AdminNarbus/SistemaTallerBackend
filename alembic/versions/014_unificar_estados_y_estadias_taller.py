"""Unificar estados a 4 canonicos, agregar campos de telemetria y crear tabla taller_solicitud_estadias

Revision ID: 014_unificar_estados_y_estadias_taller
Revises: 013_add_fecha_liberacion
Create Date: 2026-09-23 11:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '014_unificar_estados_y_estadias'
down_revision: Union[str, None] = '013_add_fecha_liberacion'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Migrar solicitudes existentes en 'REPORTADO' a 'PENDIENTE'
    if 'taller_solicitudes' in tables:
        conn.execute(sa.text("""
            UPDATE taller_solicitudes 
            SET estado = 'PENDIENTE' 
            WHERE estado = 'REPORTADO';
        """))

        columns = [c['name'] for c in inspector.get_columns('taller_solicitudes')]

        # 2. Agregar columnas de telemetria a taller_solicitudes si no existen
        if 'fecha_primer_ingreso_taller' not in columns:
            op.add_column(
                'taller_solicitudes',
                sa.Column('fecha_primer_ingreso_taller', sa.DateTime(timezone=True), nullable=True),
            )
            op.create_index(
                'ix_taller_solicitudes_fecha_primer_ingreso',
                'taller_solicitudes',
                ['fecha_primer_ingreso_taller'],
                unique=False,
            )

        if 'horas_demora_primer_ingreso' not in columns:
            op.add_column(
                'taller_solicitudes',
                sa.Column('horas_demora_primer_ingreso', sa.Numeric(10, 1), nullable=True),
            )

        if 'horas_taller_acumuladas' not in columns:
            op.add_column(
                'taller_solicitudes',
                sa.Column('horas_taller_acumuladas', sa.Numeric(10, 1), nullable=True, server_default='0.0'),
            )

    # 3. Crear tabla taller_solicitud_estadias
    if 'taller_solicitud_estadias' not in tables:
        op.create_table(
            'taller_solicitud_estadias',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('solicitud_id', sa.Integer(), sa.ForeignKey('taller_solicitudes.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('numero_visita', sa.Integer(), nullable=False, default=1),
            sa.Column('fecha_ingreso', sa.DateTime(timezone=True), nullable=False),
            sa.Column('fecha_salida', sa.DateTime(timezone=True), nullable=True),
            sa.Column('horas_estadia', sa.Numeric(10, 1), nullable=True),
            sa.Column('motivo_salida', sa.String(50), nullable=True),
        )
        op.create_index(
            'ix_taller_solicitud_estadias_solicitud_visita',
            'taller_solicitud_estadias',
            ['solicitud_id', 'numero_visita'],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'taller_solicitud_estadias' in tables:
        op.drop_table('taller_solicitud_estadias')

    if 'taller_solicitudes' in tables:
        columns = [c['name'] for c in inspector.get_columns('taller_solicitudes')]
        if 'horas_taller_acumuladas' in columns:
            op.drop_column('taller_solicitudes', 'horas_taller_acumuladas')
        if 'horas_demora_primer_ingreso' in columns:
            op.drop_column('taller_solicitudes', 'horas_demora_primer_ingreso')
        if 'fecha_primer_ingreso_taller' in columns:
            op.drop_index('ix_taller_solicitudes_fecha_primer_ingreso', table_name='taller_solicitudes')
            op.drop_column('taller_solicitudes', 'fecha_primer_ingreso_taller')
