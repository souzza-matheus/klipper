"""estado inicial

Revision ID: 0001
Revises:
Create Date: 2026-10-06

Representa o esquema como estava antes do Alembic (até as comissões).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bancos criados antes do Alembic (Base.metadata.create_all) já têm parte das tabelas: só cria as que faltam.
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if 'shops' not in existing:
        op.create_table('shops',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('address', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('owner_phone', sa.String(length=20), nullable=False),
        sa.Column('instagram', sa.String(length=80), nullable=False),
        sa.Column('pix_enabled', sa.Boolean(), nullable=False),
        sa.Column('pix_key', sa.String(length=100), nullable=False),
        sa.Column('pix_key_type', sa.String(length=10), nullable=False),
        sa.Column('pix_receiver_name', sa.String(length=25), nullable=False),
        sa.Column('pix_city', sa.String(length=15), nullable=False),
        sa.Column('pix_expire_hours', sa.Integer(), nullable=False),
        sa.Column('slot_step_minutes', sa.Integer(), nullable=False),
        sa.Column('min_advance_minutes', sa.Integer(), nullable=False),
        sa.Column('booking_days_ahead', sa.Integer(), nullable=False),
        sa.Column('reminder_minutes_before', sa.Integer(), nullable=False),
        sa.Column('cancel_min_hours', sa.Integer(), nullable=False),
        sa.Column('survey_enabled', sa.Boolean(), nullable=False),
        sa.Column('survey_delay_minutes', sa.Integer(), nullable=False),
        sa.Column('daily_summary_hour', sa.Integer(), nullable=False),
        sa.Column('last_summary_date', sa.Date(), nullable=True),
        sa.Column('welcome_text', sa.Text(), nullable=False),
        sa.Column('human_pause_hours', sa.Integer(), nullable=False),
        sa.Column('evolution_instance', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('evolution_instance')
        )

    if 'barbers' not in existing:
        op.create_table('barbers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('bio', sa.String(length=200), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('barbers', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_barbers_shop_id'), ['shop_id'], unique=False)

    if 'conversations' not in existing:
        op.create_table('conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('state', sa.String(length=40), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('paused_until', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shop_id', 'phone')
        )
        with op.batch_alter_table('conversations', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_conversations_shop_id'), ['shop_id'], unique=False)

    if 'customers' not in existing:
        op.create_table('customers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shop_id', 'phone')
        )
        with op.batch_alter_table('customers', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_customers_shop_id'), ['shop_id'], unique=False)

    if 'outbox' not in existing:
        op.create_table('outbox',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('error', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('outbox', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_outbox_phone'), ['phone'], unique=False)
            batch_op.create_index(batch_op.f('ix_outbox_shop_id'), ['shop_id'], unique=False)

    if 'services' not in existing:
        op.create_table('services',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('services', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_services_shop_id'), ['shop_id'], unique=False)

    if 'users' not in existing:
        op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('email', sa.String(length=160), nullable=False),
        sa.Column('password_hash', sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
        )
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_users_shop_id'), ['shop_id'], unique=False)

    if 'appointments' not in existing:
        op.create_table('appointments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('start', sa.DateTime(), nullable=False),
        sa.Column('end', sa.DateTime(), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('payment_status', sa.String(length=20), nullable=False),
        sa.Column('created_via', sa.String(length=10), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('reminder_sent', sa.Boolean(), nullable=False),
        sa.Column('survey_sent', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('appointments', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_appointments_barber_id'), ['barber_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_appointments_customer_id'), ['customer_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_appointments_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_appointments_start'), ['start'], unique=False)
            batch_op.create_index(batch_op.f('ix_appointments_status'), ['status'], unique=False)

    if 'barber_services' not in existing:
        op.create_table('barber_services',
        sa.Column('barber_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('barber_id', 'service_id')
        )

    if 'blocks' not in existing:
        op.create_table('blocks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=True),
        sa.Column('start', sa.DateTime(), nullable=False),
        sa.Column('end', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('blocks', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_blocks_shop_id'), ['shop_id'], unique=False)

    if 'commission_rules' not in existing:
        op.create_table('commission_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=False),
        sa.Column('beneficiary_type', sa.String(length=10), nullable=False),
        sa.Column('beneficiary_barber_id', sa.Integer(), nullable=True),
        sa.Column('percentage', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['beneficiary_barber_id'], ['barbers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('commission_rules', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_commission_rules_barber_id'), ['barber_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_commission_rules_shop_id'), ['shop_id'], unique=False)

    if 'commission_settlements' not in existing:
        op.create_table('commission_settlements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('payer_barber_id', sa.Integer(), nullable=False),
        sa.Column('beneficiary_type', sa.String(length=10), nullable=False),
        sa.Column('beneficiary_barber_id', sa.Integer(), nullable=True),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['beneficiary_barber_id'], ['barbers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['payer_barber_id'], ['barbers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('commission_settlements', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_commission_settlements_payer_barber_id'), ['payer_barber_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_commission_settlements_shop_id'), ['shop_id'], unique=False)

    if 'working_hours' not in existing:
        op.create_table('working_hours',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('start', sa.Time(), nullable=False),
        sa.Column('end', sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('working_hours', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_working_hours_barber_id'), ['barber_id'], unique=False)

    if 'payments' not in existing:
        op.create_table('payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('txid', sa.String(length=25), nullable=False),
        sa.Column('brcode', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('customer_reported_at', sa.DateTime(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('appointment_id')
        )
        with op.batch_alter_table('payments', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_payments_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_payments_status'), ['status'], unique=False)

    if 'reviews' not in existing:
        op.create_table('reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('appointment_id')
        )
        with op.batch_alter_table('reviews', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_reviews_shop_id'), ['shop_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reviews_shop_id'))

    op.drop_table('reviews')
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payments_status'))
        batch_op.drop_index(batch_op.f('ix_payments_shop_id'))

    op.drop_table('payments')
    with op.batch_alter_table('working_hours', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_working_hours_barber_id'))

    op.drop_table('working_hours')
    with op.batch_alter_table('commission_settlements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_commission_settlements_shop_id'))
        batch_op.drop_index(batch_op.f('ix_commission_settlements_payer_barber_id'))

    op.drop_table('commission_settlements')
    with op.batch_alter_table('commission_rules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_commission_rules_shop_id'))
        batch_op.drop_index(batch_op.f('ix_commission_rules_barber_id'))

    op.drop_table('commission_rules')
    with op.batch_alter_table('blocks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_blocks_shop_id'))

    op.drop_table('blocks')
    op.drop_table('barber_services')
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_appointments_status'))
        batch_op.drop_index(batch_op.f('ix_appointments_start'))
        batch_op.drop_index(batch_op.f('ix_appointments_shop_id'))
        batch_op.drop_index(batch_op.f('ix_appointments_customer_id'))
        batch_op.drop_index(batch_op.f('ix_appointments_barber_id'))

    op.drop_table('appointments')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_shop_id'))

    op.drop_table('users')
    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_services_shop_id'))

    op.drop_table('services')
    with op.batch_alter_table('outbox', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_outbox_shop_id'))
        batch_op.drop_index(batch_op.f('ix_outbox_phone'))

    op.drop_table('outbox')
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_customers_shop_id'))

    op.drop_table('customers')
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_conversations_shop_id'))

    op.drop_table('conversations')
    with op.batch_alter_table('barbers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_barbers_shop_id'))

    op.drop_table('barbers')
    op.drop_table('shops')
