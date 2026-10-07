"""CRM fase 1: equipe com papéis, comanda, estoque, pacotes, clube de assinatura, sinal, lista de espera e base da
sincronização offline

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-07

- users: role (quem já existia vira dono), barber_id, active, must_change_password, created_at;
- tabelas usadas pelo app ganham uuid (id público), updated_at, deleted_at, version e sync_seq; as linhas que já
  existem recebem um uuid e um sync_seq em ordem dentro de cada loja (shops.sync_seq guarda o último);
- tabelas novas da comanda, estoque, pacotes, assinaturas, cobranças, lista de espera e operações do sync.
Idempotente como as anteriores: bancos criados antes do Alembic (create_all) só recebem o que falta.
"""
import uuid
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SYNC_TABLES = ('services', 'barbers', 'blocks', 'customers', 'appointments')

# (tabela, coluna, fábrica da coluna) para as tabelas que já existiam. Colunas obrigatórias entram com padrão.
COLUMNS = [
    ('users', 'role', lambda: sa.Column('role', sa.String(length=15), nullable=False, server_default='owner')),
    ('users', 'barber_id', lambda: sa.Column('barber_id', sa.Integer(), nullable=True)),
    ('users', 'active', lambda: sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true())),
    ('users', 'must_change_password',
     lambda: sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false())),
    ('users', 'created_at', lambda: sa.Column('created_at', sa.DateTime(), nullable=True)),
    ('shops', 'deposit_mode', lambda: sa.Column('deposit_mode', sa.String(length=10), nullable=False,
                                                 server_default='off')),
    ('shops', 'deposit_value', lambda: sa.Column('deposit_value', sa.Numeric(precision=10, scale=2), nullable=False,
                                                  server_default='0')),
    ('shops', 'deposit_expire_minutes', lambda: sa.Column('deposit_expire_minutes', sa.Integer(), nullable=False,
                                                           server_default='30')),
    ('shops', 'deposit_refund_hours', lambda: sa.Column('deposit_refund_hours', sa.Integer(), nullable=False,
                                                         server_default='24')),
    ('shops', 'waitlist_hold_minutes', lambda: sa.Column('waitlist_hold_minutes', sa.Integer(), nullable=False,
                                                          server_default='10')),
    ('shops', 'sync_seq', lambda: sa.Column('sync_seq', sa.BigInteger(), nullable=False, server_default='0')),
    ('services', 'deposit_mode', lambda: sa.Column('deposit_mode', sa.String(length=10), nullable=False,
                                                    server_default='')),
    ('services', 'deposit_value', lambda: sa.Column('deposit_value', sa.Numeric(precision=10, scale=2),
                                                     nullable=False, server_default='0')),
    ('payments', 'kind', lambda: sa.Column('kind', sa.String(length=10), nullable=False, server_default='full')),
    ('appointments', 'checked_in_at', lambda: sa.Column('checked_in_at', sa.DateTime(), nullable=True)),
    ('appointments', 'deposit_amount', lambda: sa.Column('deposit_amount', sa.Numeric(precision=10, scale=2),
                                                          nullable=True)),
    ('appointments', 'deposit_status', lambda: sa.Column('deposit_status', sa.String(length=12), nullable=False,
                                                          server_default='none')),
    ('appointments', 'customer_package_id', lambda: sa.Column('customer_package_id', sa.Integer(), nullable=True)),
    ('appointments', 'subscription_id', lambda: sa.Column('subscription_id', sa.Integer(), nullable=True)),
]


def _sync_columns():
    # Entram aceitando nulo; depois de preenchidas viram obrigatórias
    return [
        ('uuid', lambda: sa.Column('uuid', sa.String(length=36), nullable=True)),
        ('updated_at', lambda: sa.Column('updated_at', sa.DateTime(), nullable=True)),
        ('deleted_at', lambda: sa.Column('deleted_at', sa.DateTime(), nullable=True)),
        ('version', lambda: sa.Column('version', sa.Integer(), nullable=False, server_default='1')),
        ('sync_seq', lambda: sa.Column('sync_seq', sa.BigInteger(), nullable=False, server_default='0')),
    ]


def _columns(insp, table):
    return {c['name'] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if 'products' not in tables:
        op.create_table('products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('unit', sa.String(length=10), nullable=False),
        sa.Column('cost', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('min_stock', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('commission_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('products', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_products_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_products_shop_seq', ['shop_id', 'sync_seq'], unique=False)

    if 'subscription_plans' not in tables:
        op.create_table('subscription_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('block_after_days', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('subscription_plans', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_subscription_plans_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_subscription_plans_shop_seq', ['shop_id', 'sync_seq'], unique=False)

    if 'package_plans' not in tables:
        op.create_table('package_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('sessions', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('validity_days', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('package_plans', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_package_plans_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_package_plans_shop_seq', ['shop_id', 'sync_seq'], unique=False)

    if 'service_products' not in tables:
        op.create_table('service_products',
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('service_id', 'product_id')
        )
        op.create_table('subscription_plan_items',
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('limit_per_period', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('plan_id', 'service_id')
        )
        op.create_table('subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('started_at', sa.Date(), nullable=False),
        sa.Column('next_due_date', sa.Date(), nullable=False),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('subscriptions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_subscriptions_customer_id'), ['customer_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_subscriptions_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_subscriptions_shop_seq', ['shop_id', 'sync_seq'], unique=False)
            batch_op.create_index(batch_op.f('ix_subscriptions_status'), ['status'], unique=False)

    if 'customer_packages' not in tables:
        op.create_table('customer_packages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=True),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('sessions', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('session_value', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('purchased_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.Date(), nullable=True),
        sa.Column('comanda_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['plan_id'], ['package_plans.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('customer_packages', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_customer_packages_customer_id'), ['customer_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_customer_packages_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_customer_packages_shop_seq', ['shop_id', 'sync_seq'], unique=False)

    if 'sync_operations' not in tables:
        op.create_table('sync_operations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('operation_id', sa.String(length=36), nullable=False),
        sa.Column('entity', sa.String(length=30), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shop_id', 'operation_id')
        )
        with op.batch_alter_table('sync_operations', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_sync_operations_created_at'), ['created_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_sync_operations_shop_id'), ['shop_id'], unique=False)

    if 'charges' not in tables:
        op.create_table('charges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('customer_package_id', sa.Integer(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('gateway', sa.String(length=20), nullable=False),
        sa.Column('txid', sa.String(length=35), nullable=False),
        sa.Column('brcode', sa.Text(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('customer_reported_at', sa.DateTime(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('confirmed_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['confirmed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['customer_package_id'], ['customer_packages.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('charges', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_charges_customer_id'), ['customer_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_charges_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_charges_shop_seq', ['shop_id', 'sync_seq'], unique=False)
            batch_op.create_index(batch_op.f('ix_charges_status'), ['status'], unique=False)
            batch_op.create_index(batch_op.f('ix_charges_subscription_id'), ['subscription_id'], unique=False)

    if 'comandas' not in tables:
        op.create_table('comandas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('appointment_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('opened_at', sa.DateTime(), nullable=False),
        sa.Column('opened_by_id', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('closed_by_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ),
        sa.ForeignKeyConstraint(['closed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['opened_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('appointment_id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('comandas', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_comandas_closed_at'), ['closed_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_comandas_customer_id'), ['customer_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_comandas_opened_at'), ['opened_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_comandas_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_comandas_shop_seq', ['shop_id', 'sync_seq'], unique=False)
            batch_op.create_index(batch_op.f('ix_comandas_status'), ['status'], unique=False)

    if 'waitlist_entries' not in tables:
        op.create_table('waitlist_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=True),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('after_time', sa.Time(), nullable=True),
        sa.Column('before_time', sa.Time(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('offered_at', sa.DateTime(), nullable=True),
        sa.Column('offer_expires_at', sa.DateTime(), nullable=True),
        sa.Column('offer_appointment_id', sa.Integer(), nullable=True),
        sa.Column('created_via', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['offer_appointment_id'], ['appointments.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('waitlist_entries', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_waitlist_entries_created_at'), ['created_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_waitlist_entries_customer_id'), ['customer_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_waitlist_entries_day'), ['day'], unique=False)
            batch_op.create_index(batch_op.f('ix_waitlist_entries_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_waitlist_entries_shop_seq', ['shop_id', 'sync_seq'], unique=False)
            batch_op.create_index(batch_op.f('ix_waitlist_entries_status'), ['status'], unique=False)

    if 'comanda_items' not in tables:
        op.create_table('comanda_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('comanda_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('description', sa.String(length=120), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=True),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('package_plan_id', sa.Integer(), nullable=True),
        sa.Column('barber_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('percent', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('covered_by', sa.String(length=12), nullable=False),
        sa.Column('customer_package_id', sa.Integer(), nullable=True),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('commission_base', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('reverses_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ),
        sa.ForeignKeyConstraint(['comanda_id'], ['comandas.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['customer_package_id'], ['customer_packages.id'], ),
        sa.ForeignKeyConstraint(['package_plan_id'], ['package_plans.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['reverses_id'], ['comanda_items.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('comanda_items', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_comanda_items_comanda_id'), ['comanda_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_comanda_items_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_comanda_items_shop_seq', ['shop_id', 'sync_seq'], unique=False)

    if 'comanda_payments' not in tables:
        op.create_table('comanda_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('comanda_id', sa.Integer(), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('from_deposit', sa.Boolean(), nullable=False),
        sa.Column('reverses_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['comanda_id'], ['comandas.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reverses_id'], ['comanda_payments.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('comanda_payments', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_comanda_payments_comanda_id'), ['comanda_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_comanda_payments_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_comanda_payments_shop_seq', ['shop_id', 'sync_seq'], unique=False)

    if 'package_uses' not in tables:
        op.create_table('package_uses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('customer_package_id', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=True),
        sa.Column('comanda_item_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ),
        sa.ForeignKeyConstraint(['comanda_item_id'], ['comanda_items.id'], ),
        sa.ForeignKeyConstraint(['customer_package_id'], ['customer_packages.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('package_uses', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_package_uses_customer_package_id'), ['customer_package_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_package_uses_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_package_uses_shop_seq', ['shop_id', 'sync_seq'], unique=False)

    if 'stock_movements' not in tables:
        op.create_table('stock_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column('reason', sa.String(length=12), nullable=False),
        sa.Column('unit_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('comanda_item_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['comanda_item_id'], ['comanda_items.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('stock_movements', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_stock_movements_comanda_item_id'), ['comanda_item_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_stock_movements_created_at'), ['created_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_stock_movements_product_id'), ['product_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_stock_movements_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_stock_movements_shop_seq', ['shop_id', 'sync_seq'], unique=False)

    if 'subscription_uses' not in tables:
        op.create_table('subscription_uses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=True),
        sa.Column('comanda_item_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('sync_seq', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ),
        sa.ForeignKeyConstraint(['comanda_item_id'], ['comanda_items.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )
        with op.batch_alter_table('subscription_uses', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_subscription_uses_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index('ix_subscription_uses_shop_seq', ['shop_id', 'sync_seq'], unique=False)
            batch_op.create_index(batch_op.f('ix_subscription_uses_subscription_id'), ['subscription_id'], unique=False)

    # ---- colunas novas em tabelas que já existiam
    insp = sa.inspect(bind)
    by_table: dict[str, list] = {}
    for table, col, make in COLUMNS:
        if col not in _columns(insp, table):
            by_table.setdefault(table, []).append(make())
    for table in SYNC_TABLES:
        have = _columns(insp, table)
        for col, make in _sync_columns():
            if col not in have:
                by_table.setdefault(table, []).append(make())
    for table, cols in by_table.items():
        with op.batch_alter_table(table, schema=None) as batch_op:
            for c in cols:
                batch_op.add_column(c)

    # ---- preenche uuid, updated_at e sync_seq das linhas que já existem (sync_seq em ordem, por loja)
    now = datetime.now().replace(microsecond=0)
    shops = sa.table('shops', sa.column('id', sa.Integer), sa.column('sync_seq', sa.BigInteger))
    seq = {sid: (cur or 0) for sid, cur in bind.execute(sa.select(shops.c.id, shops.c.sync_seq)).all()}
    for table in SYNC_TABLES:
        t = sa.table(table, sa.column('id', sa.Integer), sa.column('shop_id', sa.Integer),
                     sa.column('uuid', sa.String), sa.column('updated_at', sa.DateTime),
                     sa.column('sync_seq', sa.BigInteger))
        rows = bind.execute(sa.select(t.c.id, t.c.shop_id).where(t.c.uuid.is_(None)).order_by(t.c.id)).all()
        for row_id, shop_id in rows:
            seq[shop_id] = seq.get(shop_id, 0) + 1
            bind.execute(t.update().where(t.c.id == row_id).values(
                uuid=str(uuid.uuid4()), updated_at=now, sync_seq=seq[shop_id]))
    for sid, value in seq.items():
        bind.execute(shops.update().where(shops.c.id == sid).values(sync_seq=value))
    users = sa.table('users', sa.column('created_at', sa.DateTime))
    bind.execute(users.update().where(users.c.created_at.is_(None)).values(created_at=now))

    # ---- obrigatórias, únicas e índices
    insp = sa.inspect(bind)
    for table in SYNC_TABLES:
        uniques = {tuple(u['column_names']) for u in insp.get_unique_constraints(table)}
        indexes = {i['name'] for i in insp.get_indexes(table)}
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('uuid', existing_type=sa.String(length=36), nullable=False)
            batch_op.alter_column('updated_at', existing_type=sa.DateTime(), nullable=False)
            if ('uuid',) not in uniques:
                batch_op.create_unique_constraint(f'uq_{table}_uuid', ['uuid'])
            if f'ix_{table}_shop_seq' not in indexes:
                batch_op.create_index(f'ix_{table}_shop_seq', ['shop_id', 'sync_seq'], unique=False)

    fks = {(tuple(f['constrained_columns']), f['referred_table']) for f in insp.get_foreign_keys('appointments')}
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        if (('customer_package_id',), 'customer_packages') not in fks:
            batch_op.create_foreign_key('fk_appointments_customer_package_id', 'customer_packages',
                                        ['customer_package_id'], ['id'])
        if (('subscription_id',), 'subscriptions') not in fks:
            batch_op.create_foreign_key('fk_appointments_subscription_id', 'subscriptions', ['subscription_id'], ['id'])
    if (('barber_id',), 'barbers') not in {(tuple(f['constrained_columns']), f['referred_table'])
                                          for f in insp.get_foreign_keys('users')}:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.create_foreign_key('fk_users_barber_id', 'barbers', ['barber_id'], ['id'], ondelete='SET NULL')
    if (('comanda_id',), 'comandas') not in {(tuple(f['constrained_columns']), f['referred_table'])
                                            for f in insp.get_foreign_keys('customer_packages')}:
        # Fora do create_table: customer_packages é criada antes de comandas (as duas se referenciam)
        with op.batch_alter_table('customer_packages', schema=None) as batch_op:
            batch_op.create_foreign_key('fk_customer_packages_comanda_id', 'comandas', ['comanda_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('customer_packages', schema=None) as batch_op:
        batch_op.drop_constraint('fk_customer_packages_comanda_id', type_='foreignkey')
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_appointments_subscription_id', type_='foreignkey')
        batch_op.drop_constraint('fk_appointments_customer_package_id', type_='foreignkey')
    for table in ('subscription_uses', 'stock_movements', 'package_uses', 'comanda_payments', 'comanda_items',
                  'waitlist_entries', 'charges', 'sync_operations', 'customer_packages', 'comandas',
                  'subscriptions', 'subscription_plan_items', 'service_products', 'package_plans',
                  'subscription_plans', 'products'):
        op.drop_table(table)
    for table in SYNC_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(f'ix_{table}_shop_seq')
            batch_op.drop_constraint(f'uq_{table}_uuid', type_='unique')
            for col, _ in reversed(_sync_columns()):
                batch_op.drop_column(col)
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_barber_id', type_='foreignkey')
    for table, col, _ in reversed(COLUMNS):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column(col)
