"""Permitir registrar fallas resueltas antes de crear la OT.

Revision ID: 028_resolucion_historica_falla
Revises: 027_fechas_evento_registro
"""
from alembic import op


revision = "028_resolucion_historica_falla"
down_revision = "027_fechas_evento_registro"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_detalles_fechas",
        "taller_solicitud_detalles",
        type_="check",
    )


def downgrade():
    op.create_check_constraint(
        "ck_detalles_fechas",
        "taller_solicitud_detalles",
        "fecha_resolucion IS NULL OR fecha_resolucion >= fecha_creacion",
    )
