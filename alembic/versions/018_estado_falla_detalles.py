"""Add estado and motivo_incompleto to taller_solicitud_detalles.

Revision ID: 018_estado_falla_detalles
Revises: 017_fecha_actualizacion_ot
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "018_estado_falla_detalles"
down_revision: Union[str, None] = "017_fecha_actualizacion_ot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("taller_solicitud_detalles")}

    if "estado" not in columns:
        op.add_column(
            "taller_solicitud_detalles",
            sa.Column(
                "estado",
                sa.String(30),
                server_default="PENDIENTE",
                nullable=False,
            ),
        )
        op.create_index(
            "ix_taller_solicitud_detalles_estado",
            "taller_solicitud_detalles",
            ["estado"],
            unique=False,
        )

    if "motivo_incompleto" not in columns:
        op.add_column(
            "taller_solicitud_detalles",
            sa.Column(
                "motivo_incompleto",
                sa.Text(),
                nullable=True,
            ),
        )

    # Autorelleno de registros históricos existentes en BD local:
    # Solo clasificar en RESUELTA y PENDIENTE (sin incompletas ni lógica de repuestos)
    op.execute(
        """
        UPDATE taller_solicitud_detalles
        SET estado = CASE
            WHEN resuelto = true THEN 'RESUELTA'
            ELSE 'PENDIENTE'
        END
        WHERE estado IS NULL OR estado = 'PENDIENTE';
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("taller_solicitud_detalles")}

    if "motivo_incompleto" in columns:
        op.drop_column("taller_solicitud_detalles", "motivo_incompleto")

    if "estado" in columns:
        indexes = {index["name"] for index in inspector.get_indexes("taller_solicitud_detalles")}
        if "ix_taller_solicitud_detalles_estado" in indexes:
            op.drop_index("ix_taller_solicitud_detalles_estado", table_name="taller_solicitud_detalles")
        op.drop_column("taller_solicitud_detalles", "estado")
