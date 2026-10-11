import asyncio
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import create_async_engine

import app.auth.models
import app.families.models
import app.leads.models
import app.lessons.models
import app.site_content.models  # noqa: F401  (регистрируют модели в Base.metadata)
from app.core.db import Base
from tests.conftest import alembic_config

CHECK_DB = "migrations_check"


async def _recreate_database(server_url: str) -> None:
    engine = create_async_engine(server_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{CHECK_DB}"'))
        await conn.execute(text(f'CREATE DATABASE "{CHECK_DB}"'))
    await engine.dispose()


@pytest.fixture
def alembic_cfg_fresh_db(postgres_url: str) -> Config:
    asyncio.run(_recreate_database(postgres_url))
    url = make_url(postgres_url).set(database=CHECK_DB).render_as_string(hide_password=False)
    return alembic_config(url)


def _compare(conn: Connection) -> list[Any]:
    context = MigrationContext.configure(conn, opts={"compare_type": True})
    return list(compare_metadata(context, Base.metadata))


async def _diff(cfg: Config) -> list[Any]:
    url = cfg.get_main_option("sqlalchemy.url")
    assert url is not None
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        diff = await conn.run_sync(_compare)
    await engine.dispose()
    return diff


def test_upgrade_downgrade_upgrade(alembic_cfg_fresh_db: Config) -> None:
    command.upgrade(alembic_cfg_fresh_db, "head")
    command.downgrade(alembic_cfg_fresh_db, "base")
    command.upgrade(alembic_cfg_fresh_db, "head")


def test_models_match_migrations(alembic_cfg_fresh_db: Config) -> None:
    command.upgrade(alembic_cfg_fresh_db, "head")
    assert asyncio.run(_diff(alembic_cfg_fresh_db)) == []
