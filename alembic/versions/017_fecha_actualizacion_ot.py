"""Add fecha_actualizacion to taller_solicitudes.

Revision ID: 017_fecha_actualizacion_ot
Revises: 016_add_telefono_usuarios
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017_fecha_actualizacion_ot"
down_revision: Union[str, None] = "016_add_telefono_usuarios"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("taller_solicitudes")}

    if "fecha_actualizacion" not in columns:
        op.add_column(
            "taller_solicitudes",
            sa.Column(
                "fecha_actualizacion",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.execute(
            """
            UPDATE taller_solicitudes
            SET fecha_actualizacion = COALESCE(fecha_cierre, fecha_liberacion, fecha_creacion, now())
            WHERE fecha_actualizacion IS NULL
            """
        )
        op.create_index(
            "ix_taller_solicitudes_fecha_actualizacion",
            "taller_solicitudes",
            ["fecha_actualizacion"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("taller_solicitudes")}

    if "fecha_actualizacion" in columns:
        indexes = {index["name"] for index in inspector.get_indexes("taller_solicitudes")}
        if "ix_taller_solicitudes_fecha_actualizacion" in indexes:
            op.drop_index("ix_taller_solicitudes_fecha_actualizacion", table_name="taller_solicitudes")
        op.drop_column("taller_solicitudes", "fecha_actualizacion")
