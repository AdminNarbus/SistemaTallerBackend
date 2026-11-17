"""Agregar catálogo de repuestos y usos por falla.

Revision ID: 038_repuestos_por_falla
Revises: 037_merge_dashboard_neumaticos
"""
from alembic import op
import sqlalchemy as sa

revision = "038_repuestos_por_falla"
down_revision = "037_merge_dashboard_neumaticos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repuestos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(100), nullable=False),
        sa.Column("nombre", sa.String(300), nullable=False),
        sa.Column("parte", sa.String(150)),
        sa.Column("unidad", sa.String(50)),
        sa.Column("precio", sa.Numeric(16, 4)),
        sa.Column("iva", sa.Numeric(16, 4)),
        sa.Column("clasificacion", sa.String(150)),
        sa.Column("clasificacion_1", sa.String(150)),
        sa.Column("modelo", sa.String(150)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("precio IS NULL OR precio >= 0", name="ck_repuestos_precio"),
        sa.CheckConstraint("iva IS NULL OR iva >= 0", name="ck_repuestos_iva"),
    )
    op.create_index("ix_repuestos_codigo", "repuestos", ["codigo"], unique=True)
    op.create_table(
        "taller_repuestos_utilizados",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("falla_detalle_id", sa.Integer(), sa.ForeignKey("taller_solicitud_detalles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("repuesto_id", sa.Integer(), sa.ForeignKey("repuestos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("cantidad_utilizada", sa.Numeric(16, 4), nullable=False),
        sa.Column("unidad_al_registrar", sa.String(50)),
        sa.Column("usuario_registro_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("codigo_repuesto_al_registrar", sa.String(100), nullable=False),
        sa.Column("nombre_repuesto_al_registrar", sa.String(300), nullable=False),
        sa.Column("parte_repuesto_al_registrar", sa.String(150)),
        sa.Column("nombre_usuario_al_registrar", sa.String(200), nullable=False),
        sa.Column("fecha_anulacion", sa.DateTime(timezone=True)),
        sa.Column("usuario_anulacion_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="RESTRICT")),
        sa.Column("nombre_usuario_al_anular", sa.String(200)),
        sa.Column("motivo_anulacion", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("cantidad_utilizada > 0", name="ck_repuestos_utilizados_cantidad"),
        sa.CheckConstraint("(fecha_anulacion IS NULL AND usuario_anulacion_id IS NULL AND nombre_usuario_al_anular IS NULL AND motivo_anulacion IS NULL) OR (fecha_anulacion IS NOT NULL AND usuario_anulacion_id IS NOT NULL AND nombre_usuario_al_anular IS NOT NULL AND motivo_anulacion IS NOT NULL AND length(trim(motivo_anulacion)) > 0 AND fecha_anulacion >= created_at)", name="ck_repuestos_utilizados_anulacion"),
    )
    op.create_index("ix_taller_repuestos_utilizados_falla_detalle_id", "taller_repuestos_utilizados", ["falla_detalle_id"])
    op.create_index("ix_taller_repuestos_utilizados_repuesto_id", "taller_repuestos_utilizados", ["repuesto_id"])
    op.create_index("uq_repuesto_falla_vigente", "taller_repuestos_utilizados", ["falla_detalle_id", "repuesto_id"], unique=True, postgresql_where=sa.text("fecha_anulacion IS NULL"), sqlite_where=sa.text("fecha_anulacion IS NULL"))


def downgrade() -> None:
    op.drop_table("taller_repuestos_utilizados")
    op.drop_table("repuestos")
