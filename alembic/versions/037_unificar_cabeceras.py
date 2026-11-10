"""Une las cabeceras previas de dashboard y neumáticos, sin cambiar datos.

La reversión separa el grafo Alembic; no requiere DDL porque esta revisión
solamente representa la unión de las dos ramas de migración existentes.
"""

revision = "037_unificar_cabeceras"
down_revision = ("036_estado_neumaticos", "035_merge_dashboard_simulados")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Alembic unifica sus identificadores de versión; no hay cambios de esquema."""
    return None


def downgrade() -> None:
    """Alembic restaura las dos cabeceras anteriores; no hay cambios de esquema."""
    return None
