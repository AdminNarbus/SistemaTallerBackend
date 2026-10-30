"""Múltiples ejecutores por punto de pauta, preservando el revisor previo.

Revision ID: 034_pauta_mecanicos
Revises: 033_es_ot
"""
from alembic import op
import sqlalchemy as sa

revision = "034_pauta_mecanicos"
down_revision = "033_es_ot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "taller_solicitud_pauta_mecanicos",
        sa.Column("pauta_id", sa.Integer(), sa.ForeignKey("taller_solicitud_pauta.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("mecanico_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="RESTRICT"), primary_key=True, nullable=False),
    )
    op.create_index("ix_taller_solicitud_pauta_mecanicos_mecanico_id", "taller_solicitud_pauta_mecanicos", ["mecanico_id"])
    op.execute(sa.text(
        "INSERT INTO taller_solicitud_pauta_mecanicos (pauta_id, mecanico_id) "
        "SELECT id, mecanico_id FROM taller_solicitud_pauta WHERE mecanico_id IS NOT NULL"
    ))


def downgrade() -> None:
    # Evitar descartar ejecutores que la columna singular no puede representar.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM taller_solicitud_pauta_mecanicos
                           GROUP BY pauta_id HAVING count(*) > 1) THEN
                    RAISE EXCEPTION 'Cannot downgrade: checklist has multiple reviewers';
                END IF;
            END $$;
        """))
    else:
        multiples = op.get_bind().execute(sa.text(
            "SELECT pauta_id FROM taller_solicitud_pauta_mecanicos GROUP BY pauta_id HAVING count(*) > 1"
        )).first()
        if multiples:
            raise RuntimeError("Cannot downgrade: checklist has multiple reviewers")
    op.drop_index("ix_taller_solicitud_pauta_mecanicos_mecanico_id", table_name="taller_solicitud_pauta_mecanicos")
    op.drop_table("taller_solicitud_pauta_mecanicos")
