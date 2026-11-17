"""control mantenciones odometro

Revision ID: 038_control_mantenciones
Revises: 037_unificar_cabeceras
Create Date: 2026-11-10 17:27:06.721338

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "038_control_mantenciones"
down_revision = "037_unificar_cabeceras"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "control_mantenciones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bus_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=True),
        sa.Column("kilometraje", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("tipo_mantencion", sa.String(length=100), nullable=True),
        sa.Column("certificado", sa.String(length=100), nullable=True),
        sa.Column("ot", sa.String(length=100), nullable=True),
        sa.Column(
            "estado", sa.String(length=20), server_default="incompleta", nullable=False
        ),
        sa.Column(
            "activa", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("usuario_creacion_id", sa.Integer(), nullable=False),
        sa.Column("usuario_actualizacion_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('completa','incompleta')", name="ck_control_mantenciones_estado"
        ),
        sa.CheckConstraint(
            "kilometraje IS NULL OR kilometraje >= 0", name="ck_control_mantenciones_km"
        ),
        sa.ForeignKeyConstraint(["bus_id"], ["buses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["usuario_actualizacion_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["usuario_creacion_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_control_mantenciones_bus_fecha",
        "control_mantenciones",
        ["bus_id", "fecha"],
        unique=False,
    )
    op.create_table(
        "control_mantenciones_eventos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("bus_id", sa.Integer(), nullable=True),
        sa.Column("mantencion_id", sa.Integer(), nullable=True),
        sa.Column("kilometraje_id", sa.Integer(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column(
            "valores_anteriores",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "valores_nuevos",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "metadatos",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("clave_operacion", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bus_id"], ["buses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["mantencion_id"], ["control_mantenciones.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clave_operacion"),
    )
    op.create_index(
        "ix_control_eventos_bus_fecha",
        "control_mantenciones_eventos",
        ["bus_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_control_eventos_kilometraje",
        "control_mantenciones_eventos",
        ["kilometraje_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_eventos_mantencion",
        "control_mantenciones_eventos",
        ["mantencion_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_eventos_tipo_fecha",
        "control_mantenciones_eventos",
        ["tipo", "created_at"],
        unique=False,
    )
    op.create_table(
        "control_kilometrajes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bus_id", sa.Integer(), nullable=True),
        sa.Column("numero_bus_origen", sa.String(length=50), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=True),
        sa.Column("kilometraje", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("estado", sa.String(length=30), nullable=False),
        sa.Column("origen", sa.String(length=20), nullable=False),
        sa.Column("evento_carga_id", sa.Integer(), nullable=True),
        sa.Column("fila_origen", sa.Integer(), nullable=True),
        sa.Column(
            "datos_origen",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "observaciones",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("usuario_creacion_id", sa.Integer(), nullable=False),
        sa.Column("usuario_actualizacion_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado <> 'aceptado' OR (bus_id IS NOT NULL AND fecha IS NOT NULL AND kilometraje IS NOT NULL AND kilometraje >= 0)",
            name="ck_control_kilometrajes_aceptado",
        ),
        sa.CheckConstraint(
            "estado IN ('aceptado','pendiente','excluido','error','ignorado')",
            name="ck_control_kilometrajes_estado",
        ),
        sa.CheckConstraint(
            "origen IN ('excel','manual')", name="ck_control_kilometrajes_origen"
        ),
        sa.ForeignKeyConstraint(["bus_id"], ["buses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["evento_carga_id"],
            ["control_mantenciones_eventos.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_actualizacion_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["usuario_creacion_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_control_kilometrajes_bus_fecha",
        "control_kilometrajes",
        ["bus_id", "fecha"],
        unique=False,
    )
    op.create_index(
        "ix_control_kilometrajes_carga",
        "control_kilometrajes",
        ["evento_carga_id"],
        unique=False,
    )
    op.create_index(
        "ix_control_kilometrajes_estado",
        "control_kilometrajes",
        ["estado"],
        unique=False,
    )
    op.create_index(
        "uq_control_kilometrajes_aceptados",
        "control_kilometrajes",
        ["bus_id", "fecha", "kilometraje"],
        unique=True,
        postgresql_where=sa.text("estado = 'aceptado'"),
    )
    op.create_foreign_key(
        "fk_control_eventos_kilometraje",
        "control_mantenciones_eventos",
        "control_kilometrajes",
        ["kilometraje_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "buses",
        sa.Column(
            "intervalo_mantencion_km", sa.Numeric(precision=12, scale=2), nullable=True
        ),
    )
    op.create_check_constraint(
        "ck_buses_intervalo_mantencion",
        "buses",
        "intervalo_mantencion_km IS NULL OR intervalo_mantencion_km > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_buses_intervalo_mantencion", "buses", type_="check")
    op.drop_constraint(
        "fk_control_eventos_kilometraje",
        "control_mantenciones_eventos",
        type_="foreignkey",
    )
    op.drop_column("buses", "intervalo_mantencion_km")
    op.drop_index(
        "uq_control_kilometrajes_aceptados",
        table_name="control_kilometrajes",
        postgresql_where=sa.text("estado = 'aceptado'"),
    )
    op.drop_index("ix_control_kilometrajes_estado", table_name="control_kilometrajes")
    op.drop_index("ix_control_kilometrajes_carga", table_name="control_kilometrajes")
    op.drop_index(
        "ix_control_kilometrajes_bus_fecha", table_name="control_kilometrajes"
    )
    op.drop_table("control_kilometrajes")
    op.drop_index(
        "ix_control_eventos_tipo_fecha", table_name="control_mantenciones_eventos"
    )
    op.drop_index(
        "ix_control_eventos_mantencion", table_name="control_mantenciones_eventos"
    )
    op.drop_index(
        "ix_control_eventos_kilometraje", table_name="control_mantenciones_eventos"
    )
    op.drop_index(
        "ix_control_eventos_bus_fecha", table_name="control_mantenciones_eventos"
    )
    op.drop_table("control_mantenciones_eventos")
    op.drop_index(
        "ix_control_mantenciones_bus_fecha", table_name="control_mantenciones"
    )
    op.drop_table("control_mantenciones")
