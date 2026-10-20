"""Catálogo de talleres y asociación inmutable a resultados de fallas."""
from alembic import op
import sqlalchemy as sa

revision = "029_talleres_resultados"
down_revision = "028_resolucion_historica_falla"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ciudades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(nombre)) > 0", name="ck_ciudades_nombre"),
    )
    op.create_index("uq_ciudades_codigo_normalizado", "ciudades", [sa.text("lower(trim(codigo))")], unique=True)
    op.create_table(
        "talleres",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("ciudad_id", sa.Integer(), sa.ForeignKey("ciudades.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("is_activo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tipo IN ('INTERNO','EXTERNO')", name="ck_talleres_tipo"),
        sa.CheckConstraint("length(trim(nombre)) > 0", name="ck_talleres_nombre"),
    )
    op.create_index("ix_talleres_ciudad_id", "talleres", ["ciudad_id"])
    op.create_table(
        "taller_resultado_operaciones",
        sa.Column("operacion_id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("accion", sa.String(20), nullable=False),
        sa.Column("detalle_id", sa.Integer(), sa.ForeignKey("taller_solicitud_detalles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("respuesta", sa.JSON(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "taller_resultado_ubicaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evento_id", sa.Integer(), sa.ForeignKey("taller_falla_eventos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("taller_id", sa.Integer(), sa.ForeignKey("talleres.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("taller_nombre_snapshot", sa.String(200), nullable=False),
        sa.Column("taller_tipo_snapshot", sa.String(10), nullable=False),
        sa.Column("ciudad_id_snapshot", sa.Integer(), sa.ForeignKey("ciudades.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ciudad_nombre_snapshot", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_nombre_snapshot", sa.String(200), nullable=False),
        sa.Column("operacion_id", sa.String(36), nullable=False, unique=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("registrado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("evento_id", "version", name="uq_resultado_ubicacion_version"),
        sa.CheckConstraint("version > 0", name="ck_resultado_ubicacion_version"),
    )
    op.create_index("ix_taller_resultado_ubicaciones_evento_id", "taller_resultado_ubicaciones", ["evento_id"])
    op.create_table(
        "taller_resultado_colaboradores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ubicacion_id", sa.Integer(), sa.ForeignKey("taller_resultado_ubicaciones.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("taller_id", sa.Integer(), sa.ForeignKey("talleres.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("taller_nombre_snapshot", sa.String(200), nullable=False),
        sa.Column("taller_tipo_snapshot", sa.String(10), nullable=False),
        sa.Column("ciudad_id_snapshot", sa.Integer(), sa.ForeignKey("ciudades.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ciudad_nombre_snapshot", sa.String(100), nullable=False),
        sa.UniqueConstraint("ubicacion_id", "taller_id", name="uq_resultado_colaborador"),
    )
    op.create_index("ix_taller_resultado_colaboradores_ubicacion_id", "taller_resultado_colaboradores", ["ubicacion_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        CREATE FUNCTION narbus_rechazar_cambio_trazabilidad_taller() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'La trazabilidad de talleres es inmutable' USING ERRCODE='23514'; END;
        $$
        """)
        op.execute("""
        CREATE TRIGGER trg_resultado_ubicacion_inmutable
        BEFORE UPDATE OR DELETE ON taller_resultado_ubicaciones
        FOR EACH ROW EXECUTE FUNCTION narbus_rechazar_cambio_trazabilidad_taller()
        """)
        op.execute("""
        CREATE TRIGGER trg_resultado_colaborador_inmutable
        BEFORE UPDATE OR DELETE ON taller_resultado_colaboradores
        FOR EACH ROW EXECUTE FUNCTION narbus_rechazar_cambio_trazabilidad_taller()
        """)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_resultado_colaborador_inmutable ON taller_resultado_colaboradores")
        op.execute("DROP TRIGGER IF EXISTS trg_resultado_ubicacion_inmutable ON taller_resultado_ubicaciones")
        op.execute("DROP FUNCTION IF EXISTS narbus_rechazar_cambio_trazabilidad_taller()")
    op.drop_index("ix_taller_resultado_colaboradores_ubicacion_id", table_name="taller_resultado_colaboradores")
    op.drop_table("taller_resultado_colaboradores")
    op.drop_index("ix_taller_resultado_ubicaciones_evento_id", table_name="taller_resultado_ubicaciones")
    op.drop_table("taller_resultado_ubicaciones")
    op.drop_table("taller_resultado_operaciones")
    op.drop_index("ix_talleres_ciudad_id", table_name="talleres")
    op.drop_table("talleres")
    op.drop_table("ciudades")
