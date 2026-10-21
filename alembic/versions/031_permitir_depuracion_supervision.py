"""Permitir depuracion transaccional de fallas y resultados por supervision.

Revision ID: 031_depuracion_supervision
Revises: 030_ciudades_comunas_chile
"""
from alembic import op

revision = "031_depuracion_supervision"
down_revision = "030_ciudades_comunas_chile"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind and bind.dialect.name == "postgresql":
        op.execute("""
        CREATE OR REPLACE FUNCTION narbus_proteger_historial() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('narbus.permitir_depuracion', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'El historial de % es inmutable; registrar un nuevo evento', TG_TABLE_NAME
                USING ERRCODE = '23514';
        END $$;
        """)
        op.execute("""
        CREATE OR REPLACE FUNCTION narbus_rechazar_cambio_trazabilidad_taller() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('narbus.permitir_depuracion', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'La trazabilidad de talleres es inmutable' USING ERRCODE='23514';
        END;
        $$;
        """)


def downgrade():
    bind = op.get_bind()
    if bind and bind.dialect.name == "postgresql":
        op.execute("""
        CREATE OR REPLACE FUNCTION narbus_proteger_historial() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'El historial de % es inmutable; registrar un nuevo evento', TG_TABLE_NAME
                USING ERRCODE = '23514';
        END $$;
        """)
        op.execute("""
        CREATE OR REPLACE FUNCTION narbus_rechazar_cambio_trazabilidad_taller() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'La trazabilidad de talleres es inmutable' USING ERRCODE='23514';
        END;
        $$;
        """)
