"""Agregar trazabilidad inmutable por falla.

Revision ID: 020_trazabilidad_fallas
Revises: 019_comentario_adjuntos
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "020_trazabilidad_fallas"
down_revision: Union[str, None] = "019_comentario_adjuntos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    detalle_columns = {column["name"] for column in inspector.get_columns("taller_solicitud_detalles")}

    if "reportado_por_id" not in detalle_columns:
        op.add_column(
            "taller_solicitud_detalles",
            sa.Column("reportado_por_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_taller_solicitud_detalles_reportado_por_id",
            "taller_solicitud_detalles",
            "usuarios",
            ["reportado_por_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_taller_solicitud_detalles_reportado_por_id",
            "taller_solicitud_detalles",
            ["reportado_por_id"],
            unique=False,
        )
    if "fecha_reporte" not in detalle_columns:
        op.add_column(
            "taller_solicitud_detalles",
            sa.Column("fecha_reporte", sa.DateTime(timezone=True), nullable=True),
        )
    op.execute(
        "UPDATE taller_solicitud_detalles "
        "SET fecha_reporte = fecha_creacion WHERE fecha_reporte IS NULL"
    )
    indexes = {index["name"] for index in inspector.get_indexes("taller_solicitud_detalles")}
    if "ix_taller_solicitud_detalles_solicitud_fecha_reporte" not in indexes:
        op.create_index(
            "ix_taller_solicitud_detalles_solicitud_fecha_reporte",
            "taller_solicitud_detalles",
            ["solicitud_id", "fecha_reporte"],
            unique=False,
        )

    tables = set(inspector.get_table_names())
    if "taller_falla_eventos" not in tables:
        op.create_table(
            "taller_falla_eventos",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("detalle_id", sa.Integer(), nullable=False),
            sa.Column("tipo_evento", sa.String(length=50), nullable=False),
            sa.Column("usuario_actor_id", sa.Integer(), nullable=True),
            sa.Column("actor_nombre_snapshot", sa.String(length=200), nullable=False),
            sa.Column("estado_anterior", sa.String(length=30), nullable=True),
            sa.Column("estado_nuevo", sa.String(length=30), nullable=True),
            sa.Column("comentario", sa.Text(), nullable=True),
            sa.Column("fecha_evento", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["detalle_id"], ["taller_solicitud_detalles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["usuario_actor_id"], ["usuarios.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_taller_falla_eventos_detalle_id", "taller_falla_eventos", ["detalle_id"], unique=False)
        op.create_index("ix_taller_falla_eventos_tipo_evento", "taller_falla_eventos", ["tipo_evento"], unique=False)
        op.create_index("ix_taller_falla_eventos_usuario_actor_id", "taller_falla_eventos", ["usuario_actor_id"], unique=False)
        op.create_index("ix_taller_falla_eventos_fecha_evento", "taller_falla_eventos", ["fecha_evento"], unique=False)

    if "taller_falla_evento_mecanicos" not in tables:
        op.create_table(
            "taller_falla_evento_mecanicos",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("evento_id", sa.Integer(), nullable=False),
            sa.Column("mecanico_id", sa.Integer(), nullable=True),
            sa.Column("mecanico_nombre_snapshot", sa.String(length=200), nullable=False),
            sa.ForeignKeyConstraint(["evento_id"], ["taller_falla_eventos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["mecanico_id"], ["usuarios.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_taller_falla_evento_mecanicos_evento_id", "taller_falla_evento_mecanicos", ["evento_id"], unique=False)
        op.create_index("ix_taller_falla_evento_mecanicos_mecanico_id", "taller_falla_evento_mecanicos", ["mecanico_id"], unique=False)

    # Los registros históricos no permiten asegurar quién reportó la falla;
    # se preserva la fecha real sin atribuir un autor inventado.
    op.execute(
        """
        INSERT INTO taller_falla_eventos (
            detalle_id, tipo_evento, usuario_actor_id, actor_nombre_snapshot,
            estado_anterior, estado_nuevo, comentario, fecha_evento
        )
        SELECT d.id, 'REPORTADA', NULL, 'No registrado', NULL,
               COALESCE(d.estado, CASE WHEN d.resuelto THEN 'RESUELTA' ELSE 'PENDIENTE' END),
               'Evento histórico migrado', COALESCE(d.fecha_reporte, d.fecha_creacion)
        FROM taller_solicitud_detalles d
        WHERE NOT EXISTS (
            SELECT 1 FROM taller_falla_eventos e
            WHERE e.detalle_id = d.id AND e.tipo_evento = 'REPORTADA'
        )
        """
    )
    op.execute(
        """
        INSERT INTO taller_falla_eventos (
            detalle_id, tipo_evento, usuario_actor_id, actor_nombre_snapshot,
            estado_anterior, estado_nuevo, comentario, fecha_evento
        )
        SELECT d.id, 'RESUELTA', NULL, 'No registrado', 'PENDIENTE', 'RESUELTA',
               'Resolución histórica migrada', d.fecha_resolucion
        FROM taller_solicitud_detalles d
        WHERE d.resuelto = true AND d.fecha_resolucion IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM taller_falla_eventos e
              WHERE e.detalle_id = d.id AND e.tipo_evento = 'RESUELTA'
          )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "taller_falla_evento_mecanicos" in tables:
        op.drop_table("taller_falla_evento_mecanicos")
    if "taller_falla_eventos" in tables:
        op.drop_table("taller_falla_eventos")

    columns = {column["name"] for column in inspector.get_columns("taller_solicitud_detalles")}
    indexes = {index["name"] for index in inspector.get_indexes("taller_solicitud_detalles")}
    if "ix_taller_solicitud_detalles_solicitud_fecha_reporte" in indexes:
        op.drop_index("ix_taller_solicitud_detalles_solicitud_fecha_reporte", table_name="taller_solicitud_detalles")
    if "reportado_por_id" in columns:
        op.drop_index("ix_taller_solicitud_detalles_reportado_por_id", table_name="taller_solicitud_detalles")
        op.drop_constraint("fk_taller_solicitud_detalles_reportado_por_id", "taller_solicitud_detalles", type_="foreignkey")
        op.drop_column("taller_solicitud_detalles", "reportado_por_id")
    if "fecha_reporte" in columns:
        op.drop_column("taller_solicitud_detalles", "fecha_reporte")
