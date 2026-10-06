"""financeiro

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06

Forma de pagamento nos atendimentos e gastos da barbearia.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    # Banco criado pelo seed (create_all) com os modelos novos já tem tudo isso
    if 'expenses' not in insp.get_table_names():
        op.create_table('expenses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=120), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('paid_at', sa.Date(), nullable=True),
        sa.Column('payment_method', sa.String(length=10), nullable=True),
        sa.Column('barber_id', sa.Integer(), nullable=True),
        sa.Column('recurring', sa.Boolean(), nullable=False),
        sa.Column('recurring_source_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['recurring_source_id'], ['expenses.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('expenses', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_expenses_category'), ['category'], unique=False)
            batch_op.create_index(batch_op.f('ix_expenses_due_date'), ['due_date'], unique=False)
            batch_op.create_index(batch_op.f('ix_expenses_paid_at'), ['paid_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_expenses_recurring_source_id'), ['recurring_source_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_expenses_shop_id'), ['shop_id'], unique=False)

    if 'payment_method' not in {c['name'] for c in insp.get_columns('appointments')}:
        with op.batch_alter_table('appointments', schema=None) as batch_op:
            batch_op.add_column(sa.Column('payment_method', sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_column('payment_method')

    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_expenses_shop_id'))
        batch_op.drop_index(batch_op.f('ix_expenses_recurring_source_id'))
        batch_op.drop_index(batch_op.f('ix_expenses_paid_at'))
        batch_op.drop_index(batch_op.f('ix_expenses_due_date'))
        batch_op.drop_index(batch_op.f('ix_expenses_category'))

    op.drop_table('expenses')
