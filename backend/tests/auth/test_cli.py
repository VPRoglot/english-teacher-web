import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from typer.testing import CliRunner

from app.auth.models import User
from app.auth.passwords import verify_password
from app.cli import cli
from app.core.config import get_settings


async def _execute(url: str, sql: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text(sql))
    await engine.dispose()


async def _users(url: str) -> list[User]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        rows = (await conn.execute(select(User))).all()
    await engine.dispose()
    return [User(**row._mapping) for row in rows]


@pytest.fixture
def cli_env(migrated_db: str, redis_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """CLI работает с настоящей БД и коммитит — после теста таблица очищается."""
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("REDIS_URL", redis_url)
    get_settings.cache_clear()
    yield migrated_db
    asyncio.run(_execute(migrated_db, "TRUNCATE users CASCADE"))
    get_settings.cache_clear()


def test_cli_create_tutor_from_stdin(cli_env: str) -> None:
    r = CliRunner().invoke(
        cli, ["create-tutor", "--email", "T@x.ru", "--password-stdin"], input="Пароль-123 !\n"
    )
    assert r.exit_code == 0, r.output
    assert "Репетитор создан: t@x.ru" in r.output
    users = asyncio.run(_users(cli_env))
    assert len(users) == 1
    assert verify_password(users[0].password_hash, "Пароль-123 !")


def test_cli_create_tutor_with_prompt(cli_env: str) -> None:
    r = CliRunner().invoke(
        cli, ["create-tutor", "--email", "t@x.ru"], input="secret-pass\nsecret-pass\n"
    )
    assert r.exit_code == 0, r.output
    assert "Репетитор создан: t@x.ru" in r.output


def test_cli_second_tutor_fails(cli_env: str) -> None:
    runner = CliRunner()
    first = runner.invoke(
        cli, ["create-tutor", "--email", "a@x.ru", "--password-stdin"], input="secret-pass\n"
    )
    assert first.exit_code == 0, first.output
    second = runner.invoke(
        cli, ["create-tutor", "--email", "b@x.ru", "--password-stdin"], input="secret-pass\n"
    )
    assert second.exit_code == 1
    assert "Репетитор уже создан" in second.output
    assert len(asyncio.run(_users(cli_env))) == 1


def test_cli_invalid_email_fails_before_password_prompt(cli_env: str) -> None:
    r = CliRunner().invoke(cli, ["create-tutor", "--email", "not-an-email"])  # без input
    assert r.exit_code == 1
    assert "Некорректный email" in r.output
    assert "Пароль" not in r.output


def test_cli_database_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/x")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_settings.cache_clear()
    r = CliRunner().invoke(
        cli, ["create-tutor", "--email", "t@x.ru", "--password-stdin"], input="Strong-pass-1\n"
    )
    get_settings.cache_clear()
    assert r.exit_code == 1
    assert "Не удалось подключиться к базе данных" in r.output


def test_cli_integrity_error_means_tutor_already_created(monkeypatch: pytest.MonkeyPatch) -> None:
    async def race(email: str, password: str) -> str:
        raise IntegrityError("INSERT INTO users", {}, Exception("uq_users_single_tutor"))

    monkeypatch.setattr("app.cli._create_tutor", race)
    r = CliRunner().invoke(
        cli, ["create-tutor", "--email", "t@x.ru", "--password-stdin"], input="Strong-pass-1\n"
    )
    assert r.exit_code == 1
    assert "Репетитор уже создан" in r.output


def test_export_openapi(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    r = CliRunner().invoke(cli, ["export-openapi", str(out)])
    assert r.exit_code == 0, r.output
    content = out.read_text("utf-8")
    spec = json.loads(content)
    assert "/api/health" in spec["paths"]
    assert "/api/health/ready" in spec["paths"]
    assert content.endswith("}\n")
