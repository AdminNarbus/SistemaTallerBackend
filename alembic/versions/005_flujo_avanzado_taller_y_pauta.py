"""Flujo avanzado taller y pauta: asignacion atomica de fallas, pauta preventiva y control en taller

Revision ID: 005_taller_avanzado_pauta
Revises: 004_buses_table_and_fk
Create Date: 2026-09-02 16:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_taller_avanzado_pauta'
down_revision: Union[str, None] = '004_buses_table_and_fk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Columna en_taller en tabla buses
    if 'buses' in tables:
        columns_buses = [c['name'] for c in inspector.get_columns('buses')]
        if 'en_taller' not in columns_buses:
            op.add_column('buses', sa.Column('en_taller', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    # 2. Columnas en taller_solicitudes
    if 'taller_solicitudes' in tables:
        columns_sol = [c['name'] for c in inspector.get_columns('taller_solicitudes')]
        if 'motivo_incompleto_checklist' not in columns_sol:
            op.add_column('taller_solicitudes', sa.Column('motivo_incompleto_checklist', sa.Text(), nullable=True))
        if 'motivo_cierre_parcial' not in columns_sol:
            op.add_column('taller_solicitudes', sa.Column('motivo_cierre_parcial', sa.Text(), nullable=True))

        # Migrar PENDIENTE_REASIGNACION a PENDIENTE
        conn.execute(sa.text("UPDATE taller_solicitudes SET estado = 'PENDIENTE' WHERE estado = 'PENDIENTE_REASIGNACION'"))

    # 3. Columnas en taller_solicitud_detalles
    if 'taller_solicitud_detalles' in tables:
        columns_det = [c['name'] for c in inspector.get_columns('taller_solicitud_detalles')]
        if 'falta_repuesto' not in columns_det:
            op.add_column('taller_solicitud_detalles', sa.Column('falta_repuesto', sa.Boolean(), server_default=sa.text('false'), nullable=False))
        if 'comentario_repuesto' not in columns_det:
            op.add_column('taller_solicitud_detalles', sa.Column('comentario_repuesto', sa.Text(), nullable=True))

    # 4. Columnas en taller_solicitud_mecanicos
    if 'taller_solicitud_mecanicos' in tables:
        columns_mec = [c['name'] for c in inspector.get_columns('taller_solicitud_mecanicos')]
        if 'asignado_por_id' not in columns_mec:
            op.add_column('taller_solicitud_mecanicos', sa.Column('asignado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True))
        if 'duracion_minutos' not in columns_mec:
            op.add_column('taller_solicitud_mecanicos', sa.Column('duracion_minutos', sa.Integer(), nullable=True))

    # 5. Nueva tabla taller_asignacion_fallas (Asignación Atómica N:M Falla-Mecánico-Reporte)
    if 'taller_asignacion_fallas' not in tables:
        op.create_table(
            'taller_asignacion_fallas',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('solicitud_id', sa.Integer(), sa.ForeignKey('taller_solicitudes.id', ondelete='CASCADE'), nullable=False),
            sa.Column('detalle_id', sa.Integer(), sa.ForeignKey('taller_solicitud_detalles.id', ondelete='CASCADE'), nullable=False),
            sa.Column('mecanico_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='CASCADE'), nullable=False),
            sa.Column('asignado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
            sa.Column('origen', sa.String(length=50), server_default='SUPERVISOR', nullable=False),
            sa.Column('is_activo', sa.Boolean(), server_default=sa.text('true'), nullable=False),
            sa.Column('fecha_asignacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('fecha_desasignacion', sa.DateTime(timezone=True), nullable=True),
            sa.Column('resuelto_en_esta_asignacion', sa.Boolean(), server_default=sa.text('false'), nullable=False),
            sa.Column('duracion_minutos', sa.Integer(), nullable=True),
            sa.Column('comentario', sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_taller_asignacion_fallas_solicitud_id', 'taller_asignacion_fallas', ['solicitud_id'])
        op.create_index('ix_taller_asignacion_fallas_detalle_id', 'taller_asignacion_fallas', ['detalle_id'])
        op.create_index('ix_taller_asignacion_fallas_mecanico_id', 'taller_asignacion_fallas', ['mecanico_id'])
        op.create_index('ix_taller_asignacion_fallas_is_activo', 'taller_asignacion_fallas', ['is_activo'])

    # 6. Nueva tabla pauta_taller_items
    if 'pauta_taller_items' not in tables:
        pauta_items_table = op.create_table(
            'pauta_taller_items',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('categoria', sa.String(length=100), nullable=False),
            sa.Column('item', sa.String(length=255), nullable=False),
            sa.Column('orden', sa.Integer(), server_default='0', nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_pauta_taller_items_categoria', 'pauta_taller_items', ['categoria'])

        # Siembra inicial de catálogo de revisión preventiva básica (11 ítems oficiales)
        initial_items = [
            {"categoria": "MOTOR Y FLUIDOS", "item": "Niveles y fugas de aceite motor", "orden": 1, "is_active": True},
            {"categoria": "LUCES Y SISTEMA ELÉCTRICO", "item": "Control y operación de luces exteriores", "orden": 2, "is_active": True},
            {"categoria": "CLIMATIZACIÓN", "item": "Ventilación - calefacción - A/C", "orden": 3, "is_active": True},
            {"categoria": "CABINA E INSTRUMENTOS", "item": "Cuadro de instrumentos en general / Check", "orden": 4, "is_active": True},
            {"categoria": "CHASIS Y ENGRASE", "item": "Engrase", "orden": 5, "is_active": True},
            {"categoria": "MOTOR Y TRANSMISIÓN", "item": "Correas y rodillos", "orden": 6, "is_active": True},
            {"categoria": "LUCES Y SISTEMA ELÉCTRICO", "item": "Batería y terminales", "orden": 7, "is_active": True},
            {"categoria": "ESTRUCTURA Y DESGASTE", "item": "Inspección visual en cuanto a desgaste y daños", "orden": 8, "is_active": True},
            {"categoria": "MOTOR Y TRANSMISIÓN", "item": "Verificar estado de correas", "orden": 9, "is_active": True},
            {"categoria": "CARROCERÍA Y SEGURIDAD", "item": "Cerraduras - pestillos - puertas - capó", "orden": 10, "is_active": True},
            {"categoria": "CARROCERÍA Y VISIBILIDAD", "item": "Revisión de parabrisas y cristales", "orden": 11, "is_active": True},
        ]
        op.bulk_insert(pauta_items_table, initial_items)

    # 7. Nueva tabla taller_solicitud_pauta
    if 'taller_solicitud_pauta' not in tables:
        op.create_table(
            'taller_solicitud_pauta',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('solicitud_id', sa.Integer(), sa.ForeignKey('taller_solicitudes.id', ondelete='CASCADE'), nullable=False),
            sa.Column('item_id', sa.Integer(), sa.ForeignKey('pauta_taller_items.id', ondelete='CASCADE'), nullable=False),
            sa.Column('estado', sa.String(length=20), nullable=False),  # OK, DEFECTO, NO_APLICA
            sa.Column('observacion', sa.Text(), nullable=True),
            sa.Column('mecanico_id', sa.Integer(), sa.ForeignKey('usuarios.id', ondelete='SET NULL'), nullable=True),
            sa.Column('fecha_registro', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('solicitud_id', 'item_id', name='uq_solicitud_pauta_item')
        )
        op.create_index('ix_taller_solicitud_pauta_solicitud_id', 'taller_solicitud_pauta', ['solicitud_id'])
        op.create_index('ix_taller_solicitud_pauta_item_id', 'taller_solicitud_pauta', ['item_id'])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'taller_solicitud_pauta' in tables:
        op.drop_table('taller_solicitud_pauta')
    if 'pauta_taller_items' in tables:
        op.drop_table('pauta_taller_items')
    if 'taller_asignacion_fallas' in tables:
        op.drop_table('taller_asignacion_fallas')

    if 'taller_solicitud_mecanicos' in tables:
        columns_mec = [c['name'] for c in inspector.get_columns('taller_solicitud_mecanicos')]
        if 'duracion_minutos' in columns_mec:
            op.drop_column('taller_solicitud_mecanicos', 'duracion_minutos')
        if 'asignado_por_id' in columns_mec:
            op.drop_column('taller_solicitud_mecanicos', 'asignado_por_id')

    if 'taller_solicitud_detalles' in tables:
        columns_det = [c['name'] for c in inspector.get_columns('taller_solicitud_detalles')]
        if 'comentario_repuesto' in columns_det:
            op.drop_column('taller_solicitud_detalles', 'comentario_repuesto')
        if 'falta_repuesto' in columns_det:
            op.drop_column('taller_solicitud_detalles', 'falta_repuesto')

    if 'taller_solicitudes' in tables:
        columns_sol = [c['name'] for c in inspector.get_columns('taller_solicitudes')]
        if 'motivo_cierre_parcial' in columns_sol:
            op.drop_column('taller_solicitudes', 'motivo_cierre_parcial')
        if 'motivo_incompleto_checklist' in columns_sol:
            op.drop_column('taller_solicitudes', 'motivo_incompleto_checklist')

    if 'buses' in tables:
        columns_buses = [c['name'] for c in inspector.get_columns('buses')]
        if 'en_taller' in columns_buses:
            op.drop_column('buses', 'en_taller')
