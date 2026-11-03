"""Unir la carga local opcional del dashboard con el flujo vigente de taller.

Revision ID: 035_merge_dashboard_simulados
Revises: 032_dashboard_simulados_local, 034_pauta_mecanicos
"""
revision = "035_merge_dashboard_simulados"
down_revision = ("032_dashboard_simulados_local", "034_pauta_mecanicos")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass