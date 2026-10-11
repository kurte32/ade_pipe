"""Alembic environment. Migrations run with the admin identity (sa locally, migration identity in Azure)."""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context

from app.core.config import get_settings
from app.core.db import build_engine
from app.models import LEDGER_TABLES, Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    if type_ == "table" and name in LEDGER_TABLES:
        return False
    # sitio.rowversion is mapped with system=True (SQL Server fills it); autogenerate cannot see
    # system columns and would emit drop_column for it, removing the ETag/If-Match basis.
    if type_ == "column" and name == "rowversion":
        return False
    return True


def run_migrations_online() -> None:
    engine = build_engine(settings, admin=settings.db_auth == "sql")
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
