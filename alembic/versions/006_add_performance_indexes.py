"""Add performance indexes for high-frequency queries and foreign keys

Revision ID: 006_performance_indexes
Revises: 005_taller_avanzado_pauta
Create Date: 2026-09-08 12:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006_performance_indexes'
down_revision: Union[str, None] = '005_taller_avanzado_pauta'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEXES = [
    # 1. buses
    ('buses', 'ix_buses_n_bus', ['n_bus'], False),
    ('buses', 'ix_buses_is_active', ['is_active'], False),
    ('buses', 'ix_buses_en_taller', ['en_taller'], False),

    # 2. taller_solicitudes
    ('taller_solicitudes', 'ix_solicitudes_n_bus', ['n_bus'], False),
    ('taller_solicitudes', 'ix_solicitudes_estado_fecha', ['estado', 'fecha_creacion'], False),
    ('taller_solicitudes', 'ix_solicitudes_fecha_creacion', ['fecha_creacion'], False),
    ('taller_solicitudes', 'ix_solicitudes_mecanico_cierre', ['mecanico_cierre_id'], False),

    # 3. taller_solicitud_detalles
    ('taller_solicitud_detalles', 'ix_sol_detalles_sol_resuelto', ['solicitud_id', 'resuelto'], False),
    ('taller_solicitud_detalles', 'ix_sol_detalles_mecanico_resolvio', ['mecanico_resolvio_id'], False),

    # 4. fallas_taller
    ('fallas_taller', 'ix_fallas_taller_cat_active', ['categoria_id', 'is_active'], False),

    # 5. categorias_falla
    ('categorias_falla', 'ix_categorias_falla_active', ['is_active'], False),

    # 6. taller_asignacion_fallas
    ('taller_asignacion_fallas', 'ix_asig_fallas_mec_activo', ['mecanico_id', 'is_activo'], False),
    ('taller_asignacion_fallas', 'ix_asig_fallas_solicitud', ['solicitud_id'], False),

    # 7. taller_solicitud_mecanicos
    ('taller_solicitud_mecanicos', 'ix_sol_mecanicos_mec_activo', ['mecanico_id', 'is_activo'], False),

    # 8. usuarios
    ('usuarios', 'ix_usuarios_is_active', ['is_active'], False),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table_name, index_name, columns, unique in INDEXES:
        if table_name in existing_tables:
            existing_indexes = {idx['name'] for idx in inspector.get_indexes(table_name)}
            if index_name not in existing_indexes:
                # Validar que todas las columnas existan en la tabla antes de crear el índice
                col_names = {c['name'] for c in inspector.get_columns(table_name)}
                if all(col in col_names for col in columns):
                    op.create_index(index_name, table_name, columns, unique=unique)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table_name, index_name, columns, unique in reversed(INDEXES):
        if table_name in existing_tables:
            existing_indexes = {idx['name'] for idx in inspector.get_indexes(table_name)}
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name=table_name)
