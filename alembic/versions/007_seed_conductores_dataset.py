"""Seed official 124 conductores from fleet dataset

Revision ID: 007_conductores
Revises: 006_performance_indexes
Create Date: 2026-09-10 09:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.core.seeds.conductores_dataset import CONDUCTORES_DATASET

# revision identifiers, used by Alembic.
revision: str = '007_conductores'
down_revision: Union[str, None] = '006_performance_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Asegurar que el rol CONDUCTOR (id=3) exista
    conn.execute(sa.text("""
        INSERT INTO roles (id, nombre, descripcion)
        VALUES (3, 'CONDUCTOR', 'Conductor de Buses')
        ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre;
    """))

    # 2. Inserción masiva idempotente de los 124 conductores en la tabla usuarios
    insert_stmt = sa.text("""
        INSERT INTO usuarios (nombre, apellido, username, password_hash, rol_id, is_active)
        VALUES (:nombre, :apellido, :username, :password_hash, :rol_id, :is_active)
        ON CONFLICT (username) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            apellido = EXCLUDED.apellido,
            password_hash = EXCLUDED.password_hash,
            is_active = EXCLUDED.is_active;
    """)

    params = [
        {
            "nombre": c["nombre"],
            "apellido": c["apellido"],
            "username": c["rut"],
            "password_hash": c["password_hash"],
            "rol_id": 3,
            "is_active": c["is_active"],
        }
        for c in CONDUCTORES_DATASET
    ]

    conn.execute(insert_stmt, params)

    # 3. Sincronizar secuencia autoincremental de usuarios
    conn.execute(sa.text("SELECT setval('usuarios_id_seq', coalesce((SELECT max(id) FROM usuarios), 1));"))


def downgrade() -> None:
    conn = op.get_bind()
    ruts = [c["rut"] for c in CONDUCTORES_DATASET]
    conn.execute(
        sa.text("DELETE FROM usuarios WHERE username = ANY(:ruts)"),
        {"ruts": ruts}
    )
