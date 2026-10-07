"""IA: fora do tema e tokens

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-07

Registro de mensagens barradas antes do modelo e fora do tema (kind, category) e dos tokens de raciocínio e de
cache em ai_usage.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS = {
    'thinking_tokens': lambda: sa.Column('thinking_tokens', sa.Integer(), nullable=False, server_default='0'),
    'cached_tokens': lambda: sa.Column('cached_tokens', sa.Integer(), nullable=False, server_default='0'),
    'kind': lambda: sa.Column('kind', sa.String(length=10), nullable=False, server_default='call'),
    'category': lambda: sa.Column('category', sa.String(length=40), nullable=False, server_default=''),
}


def upgrade() -> None:
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('ai_usage')}
    missing = [make() for col, make in NEW_COLUMNS.items() if col not in existing]
    if missing:
        with op.batch_alter_table('ai_usage', schema=None) as batch_op:
            for col in missing:
                batch_op.add_column(col)


def downgrade() -> None:
    with op.batch_alter_table('ai_usage', schema=None) as batch_op:
        for col in reversed(list(NEW_COLUMNS)):
            batch_op.drop_column(col)
