"""Comprovantes de Pix: leitura com IA e pré-conferência

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-19

- payment_receipts: arquivo (fora da pasta pública, apagado depois do prazo de retenção), dados lidos pela IA,
  conferências, resultado e decisão; e2e_id único na plataforma (o mesmo comprovante não paga dois pagamentos);
- shops: receipt_auto_confirm e receipt_auto_confirm_max (confirmação automática, desligada por padrão).
Os comprovantes antigos (payments.receipt_data) continuam onde estão e são servidos como antes.
Idempotente como as anteriores.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHOP_COLUMNS = {
    'receipt_auto_confirm': lambda: sa.Column('receipt_auto_confirm', sa.Boolean(), nullable=False,
                                              server_default=sa.false()),
    'receipt_auto_confirm_max': lambda: sa.Column('receipt_auto_confirm_max', sa.Numeric(precision=10, scale=2),
                                                  nullable=False, server_default='0'),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existing = {c['name'] for c in insp.get_columns('shops')}
    missing = [make() for col, make in SHOP_COLUMNS.items() if col not in existing]
    if missing:
        with op.batch_alter_table('shops', schema=None) as batch_op:
            for col in missing:
                batch_op.add_column(col)

    if 'payment_receipts' not in set(insp.get_table_names()):
        op.create_table('payment_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=True),
        sa.Column('charge_id', sa.Integer(), nullable=True),
        sa.Column('file_path', sa.String(length=255), nullable=True),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('mime', sa.String(length=40), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('file_deleted_at', sa.DateTime(), nullable=True),
        sa.Column('read_status', sa.String(length=10), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('receiver_name', sa.String(length=120), nullable=True),
        sa.Column('receiver_key', sa.String(length=120), nullable=True),
        sa.Column('receiver_bank', sa.String(length=120), nullable=True),
        sa.Column('payer_name', sa.String(length=120), nullable=True),
        sa.Column('payer_bank', sa.String(length=120), nullable=True),
        sa.Column('e2e_read', sa.String(length=40), nullable=True),
        sa.Column('e2e_id', sa.String(length=40), nullable=True),
        sa.Column('doc_type', sa.String(length=20), nullable=True),
        sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('checks', sa.JSON(), nullable=True),
        sa.Column('result', sa.String(length=12), nullable=True),
        sa.Column('decision', sa.String(length=16), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decided_by_id', sa.Integer(), nullable=True),
        sa.Column('auto_confirmed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['charge_id'], ['charges.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['decided_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('e2e_id')
        )
        with op.batch_alter_table('payment_receipts', schema=None) as batch_op:
            for col in ('charge_id', 'created_at', 'customer_id', 'e2e_read', 'file_hash', 'payment_id', 'result',
                        'shop_id'):
                batch_op.create_index(batch_op.f(f'ix_payment_receipts_{col}'), [col], unique=False)


def downgrade() -> None:
    op.drop_table('payment_receipts')
    with op.batch_alter_table('shops', schema=None) as batch_op:
        for col in reversed(list(SHOP_COLUMNS)):
            batch_op.drop_column(col)
