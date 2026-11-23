"""Registro durable de notificaciones de alertas por Telegram."""
from alembic import op
import sqlalchemy as sa


revision = "044_telegram_envios"
down_revision = "043_whatsapp_solicitudes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'telegram_envios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clave', sa.String(length=64), nullable=False),
        sa.Column('solicitud_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=64), nullable=False),
        sa.Column('severidad', sa.String(length=10), nullable=False),
        sa.Column('destinatario', sa.String(length=32), nullable=False),
        sa.Column('mensaje', sa.Text(), nullable=False),
        sa.Column('estado', sa.String(length=16), nullable=False),
        sa.Column('intentos', sa.Integer(), server_default='1', nullable=False),
        sa.Column('telegram_message_id', sa.String(length=255), nullable=True),
        sa.Column('codigo_error', sa.String(length=64), nullable=True),
        sa.Column('proximo_intento', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE','ENVIANDO','ACEPTADO','FALLIDO','INCIERTO','REINTENTABLE')",
            name='ck_telegram_envios_estado',
        ),
        sa.CheckConstraint('intentos BETWEEN 1 AND 3', name='ck_telegram_envios_intentos'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('clave', name='uq_telegram_envios_clave'),
    )
    op.create_index('ix_telegram_envios_estado_reintento', 'telegram_envios', ['estado', 'proximo_intento'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_telegram_envios_estado_reintento', table_name='telegram_envios')
    op.drop_table('telegram_envios')
