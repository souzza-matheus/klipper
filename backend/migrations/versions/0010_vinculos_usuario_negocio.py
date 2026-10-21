"""Vínculo usuário–negócio e e-mail único normalizado

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-21

- memberships: um vínculo por (usuário, negócio) com o papel, o profissional (agenda), se está ativo e uma versão
  (tokens do vínculo deixam de valer quando o papel ou o acesso mudam). Cada usuário existente vira um vínculo com o
  negócio que ele tinha, com o mesmo papel e o mesmo profissional; quem estava desativado continua desativado NAQUELE
  negócio (a conta em si fica ativa, porque a desativação sempre foi feita pelo dono de um negócio);
- users: e-mail em minúsculas e sem espaços nas pontas (CHECK no banco); se dois e-mails ficarem iguais depois disso,
  a migração PARA e lista os dois, sem apagar nada (resolva à mão e rode de novo); saem shop_id, role e barber_id
  (agora no vínculo);
- shops.active: negócio suspenso (ninguém da equipe entra; os dados continuam).
Idempotente como as anteriores: roda em banco novo, em banco criado antes do Alembic e de novo sem efeito.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECK = 'ck_users_email_normalized'


def _columns(insp, table):
    return {c['name'] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'active' not in _columns(insp, 'shops'):
        with op.batch_alter_table('shops', schema=None) as batch_op:
            batch_op.add_column(sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()))

    if 'memberships' not in set(insp.get_table_names()):
        op.create_table('memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=15), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'shop_id', name='uq_memberships_user_shop')
        )
        with op.batch_alter_table('memberships', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_memberships_shop_id'), ['shop_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_memberships_user_id'), ['user_id'], unique=False)

    cols = _columns(insp, 'users')
    if 'shop_id' in cols:
        role = 'COALESCE(u.role, \'owner\')' if 'role' in cols else '\'owner\''
        barber = 'u.barber_id' if 'barber_id' in cols else 'NULL'
        active = 'COALESCE(u.active, TRUE)' if 'active' in cols else 'TRUE'
        bind.execute(sa.text(
            f"INSERT INTO memberships (user_id, shop_id, role, barber_id, active, version, created_at) "
            f"SELECT u.id, u.shop_id, {role}, {barber}, {active}, 0, u.created_at FROM users u "
            f"WHERE u.shop_id IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM memberships m WHERE m.user_id = u.id AND m.shop_id = u.shop_id)"))
        if 'active' in cols:
            bind.execute(sa.text("UPDATE users SET active = TRUE"))

    # E-mail normalizado: para (sem mexer em nada) se dois usuários virarem o mesmo e-mail
    dup = bind.execute(sa.text(
        "SELECT lower(trim(email)) AS e, COUNT(*) FROM users GROUP BY lower(trim(email)) HAVING COUNT(*) > 1")).all()
    if dup:
        raise RuntimeError("Migração 0010 parada: e-mails que ficam iguais em minúsculas e sem espaços: "
                           + ", ".join(e for e, _ in dup) + ". Troque um deles e rode a migração de novo.")
    bind.execute(sa.text("UPDATE users SET email = lower(trim(email)) WHERE email <> lower(trim(email))"))

    insp = sa.inspect(bind)
    cols = _columns(insp, 'users')
    drop = [c for c in ('shop_id', 'role', 'barber_id') if c in cols]
    has_check = CHECK in {c.get('name') for c in insp.get_check_constraints('users')}
    if drop or not has_check:
        indexes = {i['name'] for i in insp.get_indexes('users')}
        fks = [f['name'] for f in insp.get_foreign_keys('users') if set(f['constrained_columns']) & set(drop)]
        with op.batch_alter_table('users', schema=None) as batch_op:
            if 'ix_users_shop_id' in indexes and 'shop_id' in drop:
                batch_op.drop_index('ix_users_shop_id')
            if bind.dialect.name != 'sqlite':  # no SQLite o batch recria a tabela sem as chaves das colunas que saem
                for name in fks:
                    if name:
                        batch_op.drop_constraint(name, type_='foreignkey')
            for col in drop:
                batch_op.drop_column(col)
            if not has_check:
                batch_op.create_check_constraint(CHECK, 'email = lower(trim(email))')


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint(CHECK, type_='check')
        batch_op.add_column(sa.Column('shop_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('role', sa.String(length=15), nullable=False, server_default='owner'))
        batch_op.add_column(sa.Column('barber_id', sa.Integer(), nullable=True))
    # Volta para o primeiro vínculo de cada usuário (os outros negócios se perdem no downgrade)
    bind.execute(sa.text(
        "UPDATE users SET shop_id = (SELECT m.shop_id FROM memberships m WHERE m.user_id = users.id ORDER BY m.id "
        "LIMIT 1), role = COALESCE((SELECT m.role FROM memberships m WHERE m.user_id = users.id ORDER BY m.id "
        "LIMIT 1), 'owner'), barber_id = (SELECT m.barber_id FROM memberships m WHERE m.user_id = users.id "
        "ORDER BY m.id LIMIT 1)"))
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index('ix_users_shop_id', ['shop_id'], unique=False)
        batch_op.create_foreign_key('fk_users_shop_id', 'shops', ['shop_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key('fk_users_barber_id', 'barbers', ['barber_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('memberships', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_memberships_user_id'))
        batch_op.drop_index(batch_op.f('ix_memberships_shop_id'))
    op.drop_table('memberships')
    with op.batch_alter_table('shops', schema=None) as batch_op:
        batch_op.drop_column('active')
