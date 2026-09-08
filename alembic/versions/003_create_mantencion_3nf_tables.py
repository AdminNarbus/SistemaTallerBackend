"""Create mantencion 3NF tables and audit logic

Revision ID: 003_mantencion_3nf
Revises: 002_neumaticos
Create Date: 2026-08-27 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_mantencion_3nf'
down_revision: Union[str, None] = '002_neumaticos'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Crear tabla categorias_falla
    if 'categorias_falla' not in tables:
        op.create_table(
            'categorias_falla',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('nombre', sa.String(length=100), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('nombre')
        )
        op.create_index(op.f('ix_categorias_falla_id'), 'categorias_falla', ['id'], unique=False)
        op.create_index(op.f('ix_categorias_falla_nombre'), 'categorias_falla', ['nombre'], unique=True)

    # 2. Crear tabla fallas_taller
    if 'fallas_taller' not in tables:
        op.create_table(
            'fallas_taller',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('categoria_id', sa.Integer(), nullable=False),
            sa.Column('nombre', sa.String(length=150), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.ForeignKeyConstraint(['categoria_id'], ['categorias_falla.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_fallas_taller_id'), 'fallas_taller', ['id'], unique=False)
        op.create_index(op.f('ix_fallas_taller_categoria_id'), 'fallas_taller', ['categoria_id'], unique=False)

    # 3. Asegurar estructura de taller_solicitudes
    if 'taller_solicitudes' not in tables:
        op.create_table(
            'taller_solicitudes',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('n_bus', sa.String(length=50), nullable=False),
            sa.Column('usuario_creador_id', sa.Integer(), nullable=True),
            sa.Column('mecanico_cierre_id', sa.Integer(), nullable=True),
            sa.Column('estado', sa.String(length=50), server_default='REPORTADO', nullable=False),
            sa.Column('descripcion_general', sa.Text(), nullable=True),
            sa.Column('foto_url', sa.Text(), nullable=True),
            sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('fecha_cierre', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['mecanico_cierre_id'], ['usuarios.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['usuario_creador_id'], ['usuarios.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_taller_solicitudes_id'), 'taller_solicitudes', ['id'], unique=False)
        op.create_index(op.f('ix_taller_solicitudes_n_bus'), 'taller_solicitudes', ['n_bus'], unique=False)
        op.create_index(op.f('ix_taller_solicitudes_estado'), 'taller_solicitudes', ['estado'], unique=False)

    # 4. Crear tabla taller_solicitud_detalles (3NF sin categoria_id redundante)
    if 'taller_solicitud_detalles' not in tables:
        op.create_table(
            'taller_solicitud_detalles',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('solicitud_id', sa.Integer(), nullable=False),
            sa.Column('falla_id', sa.Integer(), nullable=True),
            sa.Column('descripcion_personalizada', sa.Text(), nullable=True),
            sa.Column('resuelto', sa.Boolean(), server_default='false', nullable=False),
            sa.Column('mecanico_resolvio_id', sa.Integer(), nullable=True),
            sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('fecha_resolucion', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['falla_id'], ['fallas_taller.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['mecanico_resolvio_id'], ['usuarios.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['solicitud_id'], ['taller_solicitudes.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_taller_solicitud_detalles_id'), 'taller_solicitud_detalles', ['id'], unique=False)
        op.create_index(op.f('ix_taller_solicitud_detalles_solicitud_id'), 'taller_solicitud_detalles', ['solicitud_id'], unique=False)

    # 5. Crear tabla taller_solicitud_mecanicos
    if 'taller_solicitud_mecanicos' not in tables:
        op.create_table(
            'taller_solicitud_mecanicos',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('solicitud_id', sa.Integer(), nullable=False),
            sa.Column('mecanico_id', sa.Integer(), nullable=False),
            sa.Column('es_lider_responsable', sa.Boolean(), server_default='false', nullable=False),
            sa.Column('is_activo', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('fecha_asignacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('fecha_desasignacion', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['mecanico_id'], ['usuarios.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['solicitud_id'], ['taller_solicitudes.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_taller_solicitud_mecanicos_id'), 'taller_solicitud_mecanicos', ['id'], unique=False)
        op.create_index(op.f('ix_taller_solicitud_mecanicos_solicitud_id'), 'taller_solicitud_mecanicos', ['solicitud_id'], unique=False)

    # 6. Crear tabla taller_solicitud_comentarios
    if 'taller_solicitud_comentarios' not in tables:
        op.create_table(
            'taller_solicitud_comentarios',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('solicitud_id', sa.Integer(), nullable=False),
            sa.Column('usuario_id', sa.Integer(), nullable=False),
            sa.Column('tipo', sa.String(length=50), server_default='GENERAL', nullable=False),
            sa.Column('comentario', sa.Text(), nullable=False),
            sa.Column('fecha_registro', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['solicitud_id'], ['taller_solicitudes.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_taller_solicitud_comentarios_id'), 'taller_solicitud_comentarios', ['id'], unique=False)
        op.create_index(op.f('ix_taller_solicitud_comentarios_solicitud_id'), 'taller_solicitud_comentarios', ['solicitud_id'], unique=False)

    # 7. Siembra inicial de Categorías de Falla y Fallas de Taller
    conn.execute(sa.text("""
        INSERT INTO categorias_falla (id, nombre, is_active)
        SELECT v.id, v.nombre, true
        FROM (VALUES
            (1, 'FRENOS'),
            (2, 'ELECTRICO'),
            (3, 'MOTOR'),
            (4, 'CARROCERIA'),
            (5, 'CLIMATIZACION'),
            (6, 'OTRO')
        ) AS v(id, nombre)
        WHERE NOT EXISTS (
            SELECT 1 FROM categorias_falla cf WHERE cf.nombre = v.nombre OR cf.id = v.id
        );
    """))
    conn.execute(sa.text("SELECT setval('categorias_falla_id_seq', coalesce((SELECT max(id) FROM categorias_falla), 1));"))

    conn.execute(sa.text("""
        INSERT INTO fallas_taller (categoria_id, nombre, is_active)
        SELECT c.id, f.nombre, true
        FROM (VALUES
            ('FRENOS', 'Desgaste de balatas / pastillas'),
            ('FRENOS', 'Fuga de aire en cañería de frenos'),
            ('FRENOS', 'Líquido de frenos bajo'),
            ('ELECTRICO', 'Luces principales o de freno quemadas'),
            ('ELECTRICO', 'Batería descargada o alternador defectuoso'),
            ('MOTOR', 'Fuga de aceite en carter'),
            ('MOTOR', 'Sobrecalentamiento de motor'),
            ('CARROCERIA', 'Empaquetadura o parabrisas agrietado'),
            ('CLIMATIZACION', 'Aire acondicionado no enfría'),
            ('OTRO', 'Avería general / Otro')
        ) AS f(categoria_nombre, nombre)
        JOIN categorias_falla c ON c.nombre = f.categoria_nombre
        WHERE NOT EXISTS (
            SELECT 1 FROM fallas_taller ft WHERE ft.categoria_id = c.id AND ft.nombre = f.nombre
        );
    """))
    conn.execute(sa.text("SELECT setval('fallas_taller_id_seq', coalesce((SELECT max(id) FROM fallas_taller), 1));"))


def downgrade() -> None:
    op.drop_table('taller_solicitud_comentarios')
    op.drop_table('taller_solicitud_mecanicos')
    op.drop_table('taller_solicitud_detalles')
    op.drop_table('taller_solicitudes')
    op.drop_table('fallas_taller')
    op.drop_table('categorias_falla')
