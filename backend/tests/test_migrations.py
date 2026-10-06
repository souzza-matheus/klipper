"""As migrações do Alembic criam o mesmo esquema dos modelos, inclusive em bancos criados antes do Alembic."""
import os
from argparse import Namespace

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

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


# Colunas que as migrações 0002 e 0003 adicionam em tabelas que já existiam
NEW_COLUMNS = [
    ("appointments", "payment_method"), ("appointments", "approval_requested_at"),
    ("customers", "access_status"), ("customers", "access_reason"), ("customers", "access_changed_at"),
    ("shops", "approval_expire_hours"), ("shops", "conflict_default_gap_minutes"),
]


def test_upgrade_database_created_without_alembic(tmp_path):
    """Banco antigo (create_all, sem as colunas novas e sem as tabelas novas): o upgrade completa o que falta."""
    url = f"sqlite:///{tmp_path / 'antigo.db'}"
    engine = create_engine(url)
    old_tables = [t for name, t in Base.metadata.tables.items() if name not in ("expenses", "customer_conflicts")]
    Base.metadata.create_all(engine, tables=old_tables)
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
        assert conn.exec_driver_sql("SELECT access_status, access_reason FROM customers").one() == ("normal", "")
