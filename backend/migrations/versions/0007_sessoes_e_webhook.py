"""sessões revogáveis e secret de webhook por barbearia

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07

users.token_version (revogar tokens) e shops.webhook_secret (um secret por instância da Evolution, gerado aqui para
as barbearias que já existem).

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'token_version' not in {c['name'] for c in insp.get_columns('users')}:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
    if 'webhook_secret' not in {c['name'] for c in insp.get_columns('shops')}:
        with op.batch_alter_table('shops', schema=None) as batch_op:
            batch_op.add_column(sa.Column('webhook_secret', sa.String(length=64), nullable=False, server_default=''))
    # Um secret novo para cada barbearia que ainda não tem
    shops = sa.table('shops', sa.column('id', sa.Integer), sa.column('webhook_secret', sa.String))
    for (shop_id,) in bind.execute(sa.select(shops.c.id).where(shops.c.webhook_secret == '')).all():
        bind.execute(shops.update().where(shops.c.id == shop_id).values(webhook_secret=secrets.token_urlsafe(32)))


def downgrade() -> None:
    with op.batch_alter_table('shops', schema=None) as batch_op:
        batch_op.drop_column('webhook_secret')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('token_version')
