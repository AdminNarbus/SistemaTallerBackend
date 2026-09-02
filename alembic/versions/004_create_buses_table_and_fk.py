"""Create buses table, copy data from narbus_local, and add bus_id FK to taller_solicitudes and reportes_neumaticos

Revision ID: 004_buses_table_and_fk
Revises: 003_mantencion_3nf
Create Date: 2026-08-31 17:00:00.000000

"""
from typing import Sequence, Union
import psycopg2
from psycopg2.extras import RealDictCursor
from alembic import op
import sqlalchemy as sa


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

    # 2. Migrar datos desde narbus_local si están disponibles
    try:
        source_conn = psycopg2.connect(
            dbname="narbus_local",
            user="postgres",
            password="Faber5241.",
            host="127.0.0.1",
            port=5432,
        )
        with source_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, patente, n_motor, n_chasis, n_carroceria, marca, modelo, astos,
                       coalesce("año", null) as anio, servicio, tipo_bus, empresa_id,
                       n_bus, clasificacion, min, max, tipo, max_litros, is_active
                FROM buses
                ORDER BY id
            """)
            rows = cur.fetchall()
        source_conn.close()

        if rows:
            for r in rows:
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
                    {
                        "id": r["id"],
                        "patente": r["patente"] or f"SIN-PATENTE-{r['id']}",
                        "n_motor": r["n_motor"],
                        "n_chasis": r["n_chasis"],
                        "n_carroceria": r["n_carroceria"],
                        "marca": r["marca"],
                        "modelo": r["modelo"],
                        "astos": r["astos"],
                        "anio": r["anio"],
                        "servicio": r["servicio"],
                        "tipo_bus": r["tipo_bus"],
                        "empresa_id": r["empresa_id"],
                        "n_bus": str(r["n_bus"]).strip() if r["n_bus"] else None,
                        "clasificacion": r["clasificacion"],
                        "min": r["min"],
                        "max": r["max"],
                        "tipo": r["tipo"],
                        "max_litros": r["max_litros"],
                        "is_active": True if r["is_active"] is None else r["is_active"],
                    }
                )
            # Sincronizar secuencia de id
            conn.execute(sa.text("SELECT setval('buses_id_seq', coalesce((SELECT max(id) FROM buses), 1));"))
    except Exception as e:
        print(f"[ALEMBIC 004] Advertencia al sincronizar datos desde narbus_local: {e}")

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
