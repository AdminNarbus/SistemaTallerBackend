"""Agrega el rol de consulta VISUAL."""
from alembic import op
import sqlalchemy as sa

revision = "040_rol_visual"
down_revision = "039_conductor_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        "INSERT INTO roles (nombre, descripcion) "
        "SELECT 'VISUAL', 'Solo lectura de la información de la aplicación' "
        "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE nombre = 'VISUAL')"
    ))


def downgrade() -> None:
    # La FK impide eliminar el rol si todavía existen cuentas VISUAL.
    op.execute(sa.text("DELETE FROM roles WHERE nombre = 'VISUAL'"))
