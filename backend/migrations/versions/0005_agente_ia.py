"""agente de IA

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07

Configurações de IA da barbearia, histórico da conversa usado pela IA (conversation_messages) e registro de uso
(ai_usage).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHOP_COLUMNS = {
    'ai_enabled': lambda: sa.Column('ai_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    'ai_audio_enabled': lambda: sa.Column('ai_audio_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    'ai_monthly_limit': lambda: sa.Column('ai_monthly_limit', sa.Integer(), nullable=False, server_default='3000'),
    'ai_allow_free_tier': lambda: sa.Column('ai_allow_free_tier', sa.Boolean(), nullable=False, server_default=sa.false()),
    'ai_limit_warned_month': lambda: sa.Column('ai_limit_warned_month', sa.String(length=7), nullable=True),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existing = {c['name'] for c in insp.get_columns('shops')}
    missing = [make() for col, make in SHOP_COLUMNS.items() if col not in existing]
    if missing:
        with op.batch_alter_table('shops', schema=None) as batch_op:
            for col in missing:
                batch_op.add_column(col)

    tables = insp.get_table_names()
    if 'conversation_messages' not in tables:
        op.create_table('conversation_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('channel', sa.String(length=10), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('tool_calls', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('conversation_messages', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_conversation_messages_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_conversation_messages_phone'), ['phone'], unique=False)
            batch_op.create_index(batch_op.f('ix_conversation_messages_created_at'), ['created_at'], unique=False)

    if 'ai_usage' not in tables:
        op.create_table('ai_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('model', sa.String(length=60), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('error', sa.String(length=200), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('ai_usage', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_ai_usage_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_ai_usage_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('ai_usage')
    op.drop_table('conversation_messages')
    with op.batch_alter_table('shops', schema=None) as batch_op:
        for col in reversed(list(SHOP_COLUMNS)):
            batch_op.drop_column(col)
