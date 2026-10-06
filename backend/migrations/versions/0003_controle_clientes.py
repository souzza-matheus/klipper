"""controle de clientes

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-06

Acesso do cliente ao agendamento (normal, precisa de aprovação, bloqueado), pedidos aguardando aprovação,
clientes que não podem se encontrar e as configurações da barbearia para isso.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabela, coluna) -> definição. server_default preenche as linhas que já existem.
NEW_COLUMNS = {
    ('shops', 'approval_expire_hours'): lambda: sa.Column(
        'approval_expire_hours', sa.Integer(), nullable=False, server_default='12'),
    ('shops', 'conflict_default_gap_minutes'): lambda: sa.Column(
        'conflict_default_gap_minutes', sa.Integer(), nullable=False, server_default='240'),
    ('customers', 'access_status'): lambda: sa.Column(
        'access_status', sa.String(length=10), nullable=False, server_default='normal'),
    ('customers', 'access_reason'): lambda: sa.Column(
        'access_reason', sa.Text(), nullable=False, server_default=''),
    ('customers', 'access_changed_at'): lambda: sa.Column('access_changed_at', sa.DateTime(), nullable=True),
    ('appointments', 'approval_requested_at'): lambda: sa.Column(
        'approval_requested_at', sa.DateTime(), nullable=True),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    # Banco criado pelo seed (create_all) com os modelos novos já tem tudo isso: só cria o que falta
    for table in ('shops', 'customers', 'appointments'):
        existing = {c['name'] for c in insp.get_columns(table)}
        missing = [make() for (t, col), make in NEW_COLUMNS.items() if t == table and col not in existing]
        if missing:
            with op.batch_alter_table(table, schema=None) as batch_op:
                for col in missing:
                    batch_op.add_column(col)

    if 'customer_conflicts' not in insp.get_table_names():
        op.create_table('customer_conflicts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('customer_a_id', sa.Integer(), nullable=False),
        sa.Column('customer_b_id', sa.Integer(), nullable=False),
        sa.Column('min_gap_minutes', sa.Integer(), nullable=True),
        sa.Column('same_day_block', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('customer_a_id < customer_b_id', name='ck_customer_conflicts_order'),
        sa.ForeignKeyConstraint(['customer_a_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_b_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shop_id', 'customer_a_id', 'customer_b_id')
        )
        with op.batch_alter_table('customer_conflicts', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_customer_conflicts_customer_a_id'), ['customer_a_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_customer_conflicts_customer_b_id'), ['customer_b_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_customer_conflicts_shop_id'), ['shop_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('customer_conflicts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_customer_conflicts_shop_id'))
        batch_op.drop_index(batch_op.f('ix_customer_conflicts_customer_b_id'))
        batch_op.drop_index(batch_op.f('ix_customer_conflicts_customer_a_id'))
    op.drop_table('customer_conflicts')

    for table in ('appointments', 'customers', 'shops'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            for (t, col) in NEW_COLUMNS:
                if t == table:
                    batch_op.drop_column(col)
