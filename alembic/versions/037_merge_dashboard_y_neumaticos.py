"""Unir las ramas de migración de dashboard y neumáticos.

Revision ID: 037_merge_dashboard_neumaticos
Revises: 035_merge_dashboard_simulados, 036_estado_neumaticos
"""

revision = "037_merge_dashboard_neumaticos"
down_revision = ("035_merge_dashboard_simulados", "036_estado_neumaticos")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """La unión no requiere cambios de esquema."""


def downgrade() -> None:
    """La unión no requiere cambios de esquema."""
