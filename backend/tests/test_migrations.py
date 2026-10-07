"""As migrações do Alembic criam o mesmo esquema dos modelos, inclusive em bancos criados antes do Alembic."""
import os
from argparse import Namespace

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import ForeignKey, MetaData, Table, UniqueConstraint, create_engine, inspect

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
]
# 0008: tabelas que ganharam as colunas da sincronização (uuid único, sync_seq indexado)
SYNC_TABLES = ("services", "barbers", "blocks", "customers", "appointments")
SYNC_COLUMNS = ("uuid", "updated_at", "deleted_at", "version", "sync_seq")
NEW_TABLES = ("expenses", "customer_conflicts", "conversation_messages", "ai_usage", "products", "service_products",
              "stock_movements", "package_plans", "customer_packages", "package_uses", "subscription_plans",
              "subscription_plan_items", "subscriptions", "subscription_uses", "charges", "comandas",
              "comanda_items", "comanda_payments", "waitlist_entries", "sync_operations")


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
