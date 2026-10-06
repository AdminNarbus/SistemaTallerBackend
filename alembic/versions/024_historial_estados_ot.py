"""Historial inmutable de estados de OT.

Revision ID: 024_historial_estados_ot
Revises: 023_auditoria_inmutable
"""
from alembic import op
import sqlalchemy as sa

revision = "024_historial_estados_ot"
down_revision = "023_auditoria_inmutable"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.create_table(
        "taller_solicitud_estado_eventos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("solicitud_id", sa.Integer(), nullable=False),
        sa.Column("tipo_evento", sa.String(30), nullable=False),
        sa.Column("estado_anterior", sa.String(30), nullable=True),
        sa.Column("estado_nuevo", sa.String(30), nullable=True),
        sa.Column("usuario_actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_nombre_snapshot", sa.String(200), nullable=False),
        sa.Column("fecha_evento", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("comentario_id", sa.Integer(), nullable=True),
        sa.Column("origen", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["solicitud_id"], ["taller_solicitudes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["usuario_actor_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["comentario_id", "solicitud_id"], ["taller_solicitud_comentarios.id", "taller_solicitud_comentarios.solicitud_id"], name="fk_estado_evento_comentario_ot", ondelete="RESTRICT"),
        sa.UniqueConstraint("comentario_id", name="uq_estado_evento_comentario"),
        sa.CheckConstraint("estado_anterior IS NULL OR estado_anterior IN ('REPORTADO','PENDIENTE','EN_REPARACION','LIBERADO','FINALIZADO')", name="ck_estado_evento_anterior"),
        sa.CheckConstraint("estado_nuevo IS NULL OR estado_nuevo IN ('REPORTADO','PENDIENTE','EN_REPARACION','LIBERADO','FINALIZADO')", name="ck_estado_evento_nuevo"),
        sa.CheckConstraint("origen IN ('OPERACION','BITACORA')", name="ck_estado_evento_origen"),
        sa.CheckConstraint("(tipo_evento = 'CREACION' AND estado_anterior IS NULL AND estado_nuevo IS NOT NULL) OR (tipo_evento = 'CAMBIO_ESTADO' AND estado_anterior IS NOT NULL AND estado_nuevo IS NOT NULL AND estado_anterior <> estado_nuevo) OR (tipo_evento = 'CIERRE_HISTORICO' AND origen = 'BITACORA' AND estado_anterior IS NULL AND estado_nuevo IS NULL)", name="ck_estado_evento_transicion"),
        sa.CheckConstraint("length(trim(actor_nombre_snapshot)) > 0", name="ck_estado_evento_actor"),
        sa.CheckConstraint("origen <> 'BITACORA' OR comentario_id IS NOT NULL", name="ck_estado_evento_fuente"),
    )
    op.create_index("ix_estado_evento_cronologia", "taller_solicitud_estado_eventos", ["solicitud_id", "fecha_evento", "id"])
    op.execute("CREATE TRIGGER tr_estado_eventos_inmutables BEFORE UPDATE OR DELETE ON taller_solicitud_estado_eventos FOR EACH ROW EXECUTE FUNCTION narbus_proteger_historial()")


def downgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("DROP TRIGGER tr_estado_eventos_inmutables ON taller_solicitud_estado_eventos")
    op.drop_table("taller_solicitud_estado_eventos")
