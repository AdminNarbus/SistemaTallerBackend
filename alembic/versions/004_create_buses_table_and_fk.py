"""Create buses table, copy data from narbus_local, and add bus_id FK to taller_solicitudes and reportes_neumaticos

Revision ID: 004_buses_table_and_fk
Revises: 003_mantencion_3nf
Create Date: 2026-08-31 17:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.core.seeds.buses_dataset import BUSES_DATASET


# revision identifiers, used by Alembic.
revision: str = '004_buses_table_and_fk'
down_revision: Union[str, None] = '003_mantencion_3nf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Crear tabla buses si no existe
    if 'buses' not in tables:
        op.create_table(
            'buses',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('patente', sa.String(length=100), nullable=False),
            sa.Column('n_motor', sa.Text(), nullable=True),
            sa.Column('n_chasis', sa.Text(), nullable=True),
            sa.Column('n_carroceria', sa.Text(), nullable=True),
            sa.Column('marca', sa.String(length=100), nullable=True),
            sa.Column('modelo', sa.String(length=100), nullable=True),
            sa.Column('astos', sa.String(length=50), nullable=True),
            sa.Column('anio', sa.String(length=50), nullable=True),
            sa.Column('servicio', sa.String(length=100), nullable=True),
            sa.Column('tipo_bus', sa.String(length=100), nullable=True),
            sa.Column('empresa_id', sa.Integer(), nullable=True),
            sa.Column('n_bus', sa.String(length=50), nullable=True),
            sa.Column('clasificacion', sa.String(length=50), nullable=True),
            sa.Column('min', sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column('max', sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column('tipo', sa.String(length=100), nullable=True),
            sa.Column('max_litros', sa.SmallInteger(), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('n_bus', name='uq_buses_nbus'),
        )
        op.create_index(op.f('ix_buses_id'), 'buses', ['id'], unique=False)
        op.create_index(op.f('ix_buses_n_bus'), 'buses', ['n_bus'], unique=False)
        op.create_index(op.f('ix_buses_patente'), 'buses', ['patente'], unique=False)
    else:
        columns_buses = [c['name'] for c in inspector.get_columns('buses')]
        campos = [
            ('n_motor', sa.Text()),
            ('n_chasis', sa.Text()),
            ('n_carroceria', sa.Text()),
            ('astos', sa.String(length=50)),
            ('anio', sa.String(length=50)),
            ('servicio', sa.String(length=100)),
            ('empresa_id', sa.Integer()),
            ('clasificacion', sa.String(length=50)),
            ('min', sa.Numeric(precision=5, scale=2)),
            ('max', sa.Numeric(precision=5, scale=2)),
            ('tipo', sa.String(length=100)),
            ('max_litros', sa.SmallInteger()),
        ]
        for col_name, col_type in campos:
            if col_name not in columns_buses:
                op.add_column('buses', sa.Column(col_name, col_type, nullable=True))

    # 2. Siembra estática de los 93 buses reales (rango 200 a 800) sin consultar BD externa
    for b in BUSES_DATASET:
        conn.execute(
            sa.text("""
                INSERT INTO buses (
                    id, patente, n_motor, n_chasis, n_carroceria, marca, modelo,
                    astos, anio, servicio, tipo_bus, empresa_id, n_bus,
                    clasificacion, min, max, tipo, max_litros, is_active
                ) VALUES (
                    :id, :patente, :n_motor, :n_chasis, :n_carroceria, :marca, :modelo,
                    :astos, :anio, :servicio, :tipo_bus, :empresa_id, :n_bus,
                    :clasificacion, :min, :max, :tipo, :max_litros, :is_active
                )
                ON CONFLICT (id) DO UPDATE SET
                    patente = EXCLUDED.patente,
                    n_bus = EXCLUDED.n_bus,
                    marca = EXCLUDED.marca,
                    modelo = EXCLUDED.modelo,
                    is_active = EXCLUDED.is_active;
            """),
            b
        )
    # Sincronizar secuencia de id
    conn.execute(sa.text("SELECT setval('buses_id_seq', coalesce((SELECT max(id) FROM buses), 1));"))

    # 3. Agregar bus_id a taller_solicitudes
    taller_sol_cols = [c['name'] for c in inspector.get_columns('taller_solicitudes')]
    if 'bus_id' not in taller_sol_cols:
        op.add_column('taller_solicitudes', sa.Column('bus_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_taller_solicitudes_bus_id',
            'taller_solicitudes',
            'buses',
            ['bus_id'],
            ['id'],
            ondelete='SET NULL'
        )
        op.create_index(op.f('ix_taller_solicitudes_bus_id'), 'taller_solicitudes', ['bus_id'], unique=False)

    # 4. Agregar bus_id a reportes_neumaticos
    rep_neu_cols = [c['name'] for c in inspector.get_columns('reportes_neumaticos')]
    if 'bus_id' not in rep_neu_cols:
        op.add_column('reportes_neumaticos', sa.Column('bus_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_reportes_neumaticos_bus_id',
            'reportes_neumaticos',
            'buses',
            ['bus_id'],
            ['id'],
            ondelete='SET NULL'
        )
        op.create_index(op.f('ix_reportes_neumaticos_bus_id'), 'reportes_neumaticos', ['bus_id'], unique=False)

    # 5. Población de bus_id existente en base a n_bus
    conn.execute(sa.text("""
        UPDATE taller_solicitudes ts
        SET bus_id = b.id
        FROM buses b
        WHERE b.n_bus = ts.n_bus AND ts.bus_id IS NULL;
    """))
    conn.execute(sa.text("""
        UPDATE reportes_neumaticos rn
        SET bus_id = b.id
        FROM buses b
        WHERE b.n_bus = rn.n_bus AND rn.bus_id IS NULL;
    """))


def downgrade() -> None:
    op.drop_constraint('fk_reportes_neumaticos_bus_id', 'reportes_neumaticos', type_='foreignkey')
    op.drop_index(op.f('ix_reportes_neumaticos_bus_id'), table_name='reportes_neumaticos')
    op.drop_column('reportes_neumaticos', 'bus_id')

    op.drop_constraint('fk_taller_solicitudes_bus_id', 'taller_solicitudes', type_='foreignkey')
    op.drop_index(op.f('ix_taller_solicitudes_bus_id'), table_name='taller_solicitudes')
    op.drop_column('taller_solicitudes', 'bus_id')

    op.drop_index(op.f('ix_buses_patente'), table_name='buses')
    op.drop_index(op.f('ix_buses_n_bus'), table_name='buses')
    op.drop_index(op.f('ix_buses_id'), table_name='buses')
    op.drop_table('buses')
