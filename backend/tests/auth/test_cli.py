import asyncio
import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from typer.testing import CliRunner

from app.auth.models import User
from app.auth.passwords import verify_password
from app.auth.sessions import SessionStore
from app.cli import cli
from app.core.config import get_settings
from tests.factories import make_child, make_family, make_parent


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


def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Обязательные настройки, не относящиеся к тесту: реальный .env их не даёт."""
    monkeypatch.setenv("REVALIDATE_SECRET", "test-revalidate-secret")
    monkeypatch.setenv("S3_BUCKET", "media-test")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret-key")


@pytest.fixture
def cli_env(migrated_db: str, redis_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """CLI работает с настоящей БД и коммитит — после теста таблица очищается."""
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("REDIS_URL", redis_url)
    _set_required_env(monkeypatch)
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
    _set_required_env(monkeypatch)
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


async def _make_archived_family(url: str, *, archived: bool = True) -> str:
    engine = create_async_engine(url)
    async with AsyncSession(engine) as session:
        family = await make_family(session, name="Ивановы", archived=archived)
        await make_parent(session, family)
        await make_child(session, family, username="masha")
        family_id = str(family.id)
        await session.commit()
    await engine.dispose()
    return family_id


async def _count(url: str, table: str) -> int:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        total = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
    await engine.dispose()
    return int(total)


@pytest.fixture
def purge_env(cli_env: str) -> Iterator[str]:
    yield cli_env
    asyncio.run(_execute(cli_env, "TRUNCATE families CASCADE"))


def test_purge_cli_prompts_and_aborts(purge_env: str) -> None:
    family_id = asyncio.run(_make_archived_family(purge_env))
    r = CliRunner().invoke(cli, ["purge-family", family_id], input="n\n")
    assert r.exit_code == 1
    assert "Ивановы: пользователей 2, детей 1, занятий 0, запросов 0, заявок 0" in r.output
    assert r.output.index("Ивановы") < r.output.index("Удалить?")
    assert "Отменено" in r.output
    assert asyncio.run(_count(purge_env, "families")) == 1
    assert asyncio.run(_count(purge_env, "users")) == 2


def test_purge_cli_yes(purge_env: str) -> None:
    family_id = asyncio.run(_make_archived_family(purge_env))
    r = CliRunner().invoke(cli, ["purge-family", family_id, "--yes"])
    assert r.exit_code == 0, r.output
    assert "Семья удалена: Ивановы: пользователей 2, детей 1" in r.output
    assert asyncio.run(_count(purge_env, "families")) == 0
    assert asyncio.run(_count(purge_env, "users")) == 0


def test_purge_cli_redis_down_after_commit(purge_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    async def redis_down(self: SessionStore, user_id: uuid.UUID) -> int:
        raise RedisConnectionError("redis недоступен")

    monkeypatch.setattr(SessionStore, "delete_all_for_user", redis_down)
    family_id = asyncio.run(_make_archived_family(purge_env))
    r = CliRunner().invoke(cli, ["purge-family", family_id, "--yes"])
    assert r.exit_code == 0, r.output
    assert "Семья удалена: Ивановы: пользователей 2, детей 1" in r.output
    assert (
        "Сессии не отозваны (Redis недоступен) — они уже недействительны: пользователей больше нет."
    ) in r.output
    assert "Не удалось подключиться" not in r.output
    assert asyncio.run(_count(purge_env, "users")) == 0


def test_purge_cli_not_archived(purge_env: str) -> None:
    family_id = asyncio.run(_make_archived_family(purge_env, archived=False))
    r = CliRunner().invoke(cli, ["purge-family", family_id, "--yes"])
    assert r.exit_code == 1
    assert "Сначала переведите семью в архив" in r.output
    assert asyncio.run(_count(purge_env, "families")) == 1


def test_purge_cli_unknown_family(purge_env: str) -> None:
    r = CliRunner().invoke(cli, ["purge-family", str(uuid.uuid4()), "--yes"])
    assert r.exit_code == 1
    assert "Семья не найдена" in r.output


def test_purge_cli_database_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/x")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    _set_required_env(monkeypatch)
    get_settings.cache_clear()
    r = CliRunner().invoke(cli, ["purge-family", str(uuid.uuid4()), "--yes"])
    get_settings.cache_clear()
    assert r.exit_code == 1
    assert "Не удалось подключиться" in r.output
