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


def test_upgrade_database_created_without_alembic(tmp_path):
    """Banco antigo (create_all, sem a coluna nova e sem a tabela de gastos): o upgrade completa o que falta."""
    url = f"sqlite:///{tmp_path / 'antigo.db'}"
    engine = create_engine(url)
    old_tables = [t for name, t in Base.metadata.tables.items() if name != "expenses"]
    Base.metadata.create_all(engine, tables=old_tables)
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE appointments DROP COLUMN payment_method")
    assert "payment_method" not in {c["name"] for c in inspect(engine).get_columns("appointments")}
    _upgrade(url)
    assert _diff(url) == []
    assert "alembic_version" in inspect(create_engine(url)).get_table_names()
