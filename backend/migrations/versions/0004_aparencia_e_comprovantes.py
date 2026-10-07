"""aparência, ação de conflito e comprovantes

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-07

Segmento do negócio (niche) e modo do tema (theme_mode), o que fazer quando um cliente cai perto de outro em
conflito (conflict_action) e o comprovante de Pix mandado pelo cliente no WhatsApp.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabela, coluna) -> definição. server_default preenche as linhas que já existem.
NEW_COLUMNS = {
    ('shops', 'niche'): lambda: sa.Column('niche', sa.String(length=20), nullable=False, server_default='barbershop'),
    ('shops', 'theme_mode'): lambda: sa.Column('theme_mode', sa.String(length=10), nullable=False, server_default='auto'),
    ('customer_conflicts', 'conflict_action'): lambda: sa.Column(
        'conflict_action', sa.String(length=10), nullable=False, server_default='block'),
    ('payments', 'receipt_mime'): lambda: sa.Column('receipt_mime', sa.String(length=60), nullable=True),
    ('payments', 'receipt_data'): lambda: sa.Column('receipt_data', sa.LargeBinary(), nullable=True),
    ('payments', 'receipt_at'): lambda: sa.Column('receipt_at', sa.DateTime(), nullable=True),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    # Banco criado pelo seed (create_all) com os modelos novos já tem tudo isso: só cria o que falta
    for table in ('shops', 'customer_conflicts', 'payments'):
        existing = {c['name'] for c in insp.get_columns(table)}
        missing = [make() for (t, col), make in NEW_COLUMNS.items() if t == table and col not in existing]
        if missing:
            with op.batch_alter_table(table, schema=None) as batch_op:
                for col in missing:
                    batch_op.add_column(col)


def downgrade() -> None:
    for (table, col) in reversed(list(NEW_COLUMNS)):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column(col)
