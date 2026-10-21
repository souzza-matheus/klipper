"""As migrações do Alembic criam o mesmo esquema dos modelos, inclusive em bancos criados antes do Alembic."""
import os
from argparse import Namespace

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import (
    Column, ForeignKey, Integer, MetaData, String, Table, UniqueConstraint, create_engine, inspect,
)

from app.db import Base

BACKEND = os.path.dirname(os.path.dirname(__file__))


def _upgrade(url: str) -> None:
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "migrations"))
    cfg.cmd_opts = Namespace(x=[f"url={url}"])
    command.upgrade(cfg, "head")


def _diff(url: str) -> list:
    engine = create_engine(url)
    with engine.connect() as conn:
        return compare_metadata(MigrationContext.configure(conn), Base.metadata)


def test_upgrade_from_empty_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'novo.db'}"
    _upgrade(url)
    assert _diff(url) == []


# Colunas que as migrações 0002 a 0004 adicionam em tabelas que já existiam
NEW_COLUMNS = [
    ("appointments", "payment_method"), ("appointments", "approval_requested_at"),
    ("customers", "access_status"), ("customers", "access_reason"), ("customers", "access_changed_at"),
    ("shops", "approval_expire_hours"), ("shops", "conflict_default_gap_minutes"),
    ("shops", "niche"), ("shops", "theme_mode"),
    ("payments", "receipt_mime"), ("payments", "receipt_data"), ("payments", "receipt_at"),
    ("shops", "ai_enabled"), ("shops", "ai_audio_enabled"), ("shops", "ai_monthly_limit"),
    ("shops", "ai_allow_free_tier"), ("shops", "ai_limit_warned_month"),
    ("shops", "webhook_secret"), ("users", "token_version"),
    # 0008: CRM fase 1
    ("users", "role"), ("users", "active"), ("users", "must_change_password"), ("users", "created_at"),
    ("shops", "deposit_mode"), ("shops", "deposit_value"), ("shops", "deposit_expire_minutes"),
    ("shops", "deposit_refund_hours"), ("shops", "waitlist_hold_minutes"), ("shops", "sync_seq"),
    ("services", "deposit_mode"), ("services", "deposit_value"), ("payments", "kind"),
    ("appointments", "checked_in_at"), ("appointments", "deposit_amount"), ("appointments", "deposit_status"),
    # 0009: comprovantes
    ("shops", "receipt_auto_confirm"), ("shops", "receipt_auto_confirm_max"),
    # 0010: negócio suspenso
    ("shops", "active"),
]
# 0008: tabelas que ganharam as colunas da sincronização (uuid único, sync_seq indexado)
SYNC_TABLES = ("services", "barbers", "blocks", "customers", "appointments")
SYNC_COLUMNS = ("uuid", "updated_at", "deleted_at", "version", "sync_seq")
NEW_TABLES = ("expenses", "customer_conflicts", "conversation_messages", "ai_usage", "products", "service_products",
              "stock_movements", "package_plans", "customer_packages", "package_uses", "subscription_plans",
              "subscription_plan_items", "subscriptions", "subscription_uses", "charges", "comandas",
              "comanda_items", "comanda_payments", "waitlist_entries", "sync_operations", "payment_receipts",
              "memberships")


def _old_metadata() -> MetaData:
    """Esquema "antigo": sem as tabelas novas e, nas que existiam, sem as colunas da sincronização (e sem as
    referências do agendamento para pacote e assinatura e do usuário para o profissional)."""
    md = MetaData()
    for name, t in Base.metadata.tables.items():
        if name in NEW_TABLES:
            continue
        drop = set(SYNC_COLUMNS) if name in SYNC_TABLES else set()
        drop |= {"appointments": {"customer_package_id", "subscription_id"}, "users": {"barber_id"}}.get(name, set())
        cols = []
        if name == "users":  # antes da 0010 o usuário tinha um negócio só, com o papel nele
            cols += [Column("shop_id", Integer, ForeignKey("shops.id", ondelete="CASCADE"), index=True),
                     Column("role", String(15))]
        for c in t.columns:
            if c.name not in drop:
                col = c._copy()
                for fk in c.foreign_keys:  # _copy() não leva as chaves estrangeiras
                    col.append_foreign_key(ForeignKey(fk.target_fullname, ondelete=fk.ondelete))
                cols.append(col)
        uniques = [UniqueConstraint(*[c.name for c in u.columns]) for u in t.constraints
                   if isinstance(u, UniqueConstraint) and len(u.columns) > 1]
        Table(name, md, *cols, *uniques)
    return md


def test_upgrade_database_created_without_alembic(tmp_path):
    """Banco antigo (create_all, sem as colunas novas e sem as tabelas novas): o upgrade completa o que falta."""
    url = f"sqlite:///{tmp_path / 'antigo.db'}"
    engine = create_engine(url)
    _old_metadata().create_all(engine)
    with engine.begin() as conn:
        for table, col in NEW_COLUMNS:
            conn.exec_driver_sql(f"ALTER TABLE {table} DROP COLUMN {col}")
        conn.exec_driver_sql("INSERT INTO shops (name, address, phone, owner_phone, instagram, pix_enabled, pix_key, "
                             "pix_key_type, pix_receiver_name, pix_city, pix_expire_hours, slot_step_minutes, "
                             "min_advance_minutes, booking_days_ahead, reminder_minutes_before, cancel_min_hours, "
                             "survey_enabled, survey_delay_minutes, daily_summary_hour, welcome_text, "
                             "human_pause_hours, evolution_instance, created_at) VALUES ('Antiga', '', '', '', '', 0, "
                             "'', 'random', '', '', 12, 30, 30, 7, 120, 2, 1, 30, 8, '', 3, 'antiga', '2026-01-01')")
        conn.exec_driver_sql("INSERT INTO customers (shop_id, phone, name, notes, created_at) "
                             "VALUES (1, '5531900000000', 'Cliente antigo', '', '2026-01-01')")
    assert "payment_method" not in {c["name"] for c in inspect(engine).get_columns("appointments")}
    _upgrade(url)
    assert _diff(url) == []
    assert "alembic_version" in inspect(create_engine(url)).get_table_names()
    # Linhas que já existiam recebem os padrões
    with create_engine(url).connect() as conn:
        assert conn.exec_driver_sql("SELECT approval_expire_hours, conflict_default_gap_minutes FROM shops").one() == (12, 240)
        assert conn.exec_driver_sql("SELECT niche, theme_mode FROM shops").one() == ("barbershop", "auto")
        # Cada barbearia antiga ganha um secret de webhook próprio
        assert len(conn.exec_driver_sql("SELECT webhook_secret FROM shops").scalar()) >= 32
        assert conn.exec_driver_sql("SELECT access_status, access_reason FROM customers").one() == ("normal", "")
        # Sincronização: cada linha antiga ganha um uuid e um sync_seq; a loja guarda o último
        uid, seq, version = conn.exec_driver_sql("SELECT uuid, sync_seq, version FROM customers").one()
        assert len(uid) == 36 and seq == 1 and version == 1
        assert conn.exec_driver_sql("SELECT sync_seq, deposit_mode FROM shops").one() == (1, "off")


def _db_before_0010(tmp_path, users):
    """Banco na versão 0009 (um negócio por usuário, com o papel na tabela users)."""
    url = f"sqlite:///{tmp_path / 'v0009.db'}"
    cfg = Config(os.path.join(BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND, "migrations"))
    cfg.cmd_opts = Namespace(x=[f"url={url}"])
    command.upgrade(cfg, "0009")
    with create_engine(url).begin() as conn:
        for shop in ("Loja A", "Loja B"):
            conn.exec_driver_sql(
                "INSERT INTO shops (name, address, phone, owner_phone, instagram, pix_enabled, pix_key, pix_key_type, "
                "pix_receiver_name, pix_city, pix_expire_hours, slot_step_minutes, min_advance_minutes, "
                "booking_days_ahead, reminder_minutes_before, cancel_min_hours, survey_enabled, survey_delay_minutes, "
                "daily_summary_hour, welcome_text, human_pause_hours, evolution_instance, created_at, sync_seq, "
                "deposit_mode, deposit_value, deposit_expire_minutes, deposit_refund_hours, waitlist_hold_minutes, "
                "niche, theme_mode, ai_enabled, ai_audio_enabled, ai_monthly_limit, ai_allow_free_tier, "
                "webhook_secret, approval_expire_hours, conflict_default_gap_minutes, receipt_auto_confirm, "
                "receipt_auto_confirm_max) VALUES "
                f"('{shop}', '', '', '', '', 0, '', 'random', '', '', 12, 30, 30, 7, 120, 2, 1, 30, 8, '', 3, "
                f"'{shop}', '2026-01-01', 0, 'off', 0, 30, 24, 10, 'barbershop', 'auto', 0, 0, 3000, 0, 'x', 12, "
                "240, 0, 0)")
        for shop_id, email, role, active in users:
            conn.exec_driver_sql(
                "INSERT INTO users (shop_id, name, email, password_hash, token_version, role, active, "
                f"must_change_password, created_at) VALUES ({shop_id}, 'P', '{email}', 'h', 0, '{role}', {active}, 0, "
                "'2026-01-01')")
    return url, cfg


def test_0010_turns_each_user_into_a_membership(tmp_path):
    """Cada usuário vira um vínculo com o negócio que tinha, com o mesmo papel; desativado continua desativado
    naquele negócio; o e-mail fica normalizado; nada se perde."""
    url, cfg = _db_before_0010(tmp_path, [(1, " Dono@Loja.com ", "owner", 1), (1, "rec@loja.com", "reception", 0),
                                          (2, "pro@lojab.com", "professional", 1)])
    command.upgrade(cfg, "head")
    assert _diff(url) == []
    with create_engine(url).connect() as conn:
        users = conn.exec_driver_sql("SELECT id, email, active FROM users ORDER BY id").all()
        assert [u[1] for u in users] == ["dono@loja.com", "rec@loja.com", "pro@lojab.com"]
        assert all(u[2] for u in users)  # a conta fica ativa; quem estava desativado perde só o negócio
        rows = conn.exec_driver_sql("SELECT user_id, shop_id, role, active, version FROM memberships "
                                    "ORDER BY user_id").all()
        assert rows == [(1, 1, "owner", 1, 0), (2, 1, "reception", 0, 0), (3, 2, "professional", 1, 0)]
        cols = {c["name"] for c in inspect(conn).get_columns("users")}
        assert not cols & {"shop_id", "role", "barber_id"}
    command.upgrade(cfg, "head")  # de novo: sem efeito


def test_0010_stops_on_emails_that_collide_after_normalizing(tmp_path):
    import pytest
    url, cfg = _db_before_0010(tmp_path, [(1, "Ana@Loja.com", "owner", 1), (2, "ana@loja.com", "owner", 1)])
    with pytest.raises(RuntimeError, match="ana@loja.com"):
        command.upgrade(cfg, "head")
    with create_engine(url).connect() as conn:  # nada foi apagado
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM users").scalar() == 2
