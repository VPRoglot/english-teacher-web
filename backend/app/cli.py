import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Annotated

import typer
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError

from app.auth.identity import normalize_email
from app.auth.service import create_tutor
from app.core.config import Settings, get_settings
from app.core.db import create_db_engine, create_sessionmaker
from app.core.errors import AppError
from app.core.redis import create_redis
from app.families.purge import PurgeSummary, describe_purge, purge_family
from app.main import create_app

cli = typer.Typer(no_args_is_help=True, help="Служебные команды backend.")


async def _create_tutor(email: str, password: str) -> str:
    engine = create_db_engine(get_settings())
    try:
        async with create_sessionmaker(engine)() as session:
            user = await create_tutor(session, email=email, password=password)
            await session.commit()
            return user.email or email
    finally:
        await engine.dispose()


@cli.command("create-tutor")
def create_tutor_command(
    email: Annotated[str, typer.Option(help="Email репетитора (логин).")],
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="Прочитать пароль из stdin.")
    ] = False,
) -> None:
    """Создать учётную запись репетитора (она может быть только одна)."""
    try:
        normalize_email(email)  # неверный email — до запроса пароля
    except AppError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1) from exc
    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = typer.prompt("Пароль", hide_input=True, confirmation_prompt=True)
    try:
        created = asyncio.run(_create_tutor(email, password))
    except AppError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1) from exc
    except IntegrityError as exc:  # гонка: второй репетитор создан параллельно
        typer.echo("Репетитор уже создан", err=True)
        raise typer.Exit(1) from exc
    except (OSError, OperationalError, InterfaceError) as exc:
        typer.echo("Не удалось подключиться к базе данных: проверьте DATABASE_URL", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Репетитор создан: {created}")


def _summary_line(summary: PurgeSummary) -> str:
    return (
        f"{summary.family_name}: пользователей {summary.users}, детей {summary.children}, "
        f"занятий {summary.lessons}, запросов {summary.change_requests}, заявок {summary.leads}"
    )


async def _describe_purge(family_id: uuid.UUID) -> PurgeSummary:
    engine = create_db_engine(get_settings())
    try:
        async with create_sessionmaker(engine)() as session:
            return await describe_purge(session, family_id)
    finally:
        await engine.dispose()


async def _purge_family(family_id: uuid.UUID) -> PurgeSummary:
    settings = get_settings()
    engine = create_db_engine(settings)
    redis = create_redis(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            return await purge_family(session, redis, family_id)
    finally:
        await redis.aclose()
        await engine.dispose()


@cli.command("purge-family")
def purge_family_command(
    family_id: Annotated[uuid.UUID, typer.Argument(help="Идентификатор архивной семьи.")],
    yes: Annotated[bool, typer.Option("--yes", help="Не спрашивать подтверждение.")] = False,
) -> None:
    """Навсегда удалить архивную семью и все её данные (152-ФЗ). Действие необратимо."""
    try:
        summary = asyncio.run(_describe_purge(family_id))
        typer.echo(f"Будет удалено безвозвратно. {_summary_line(summary)}")
        if not yes and not typer.confirm("Удалить?"):
            typer.echo("Отменено", err=True)
            raise typer.Exit(1)
        summary = asyncio.run(_purge_family(family_id))
    except AppError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1) from exc
    except (OSError, OperationalError, InterfaceError, RedisError) as exc:
        typer.echo(
            "Не удалось подключиться к базе данных или Redis: проверьте DATABASE_URL и REDIS_URL",
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(f"Семья удалена: {_summary_line(summary)}")


@cli.command("export-openapi")
def export_openapi(
    path: Annotated[Path, typer.Argument(help="Куда записать openapi.json.")],
) -> None:
    """Выгрузить OpenAPI-схему (для генерации frontend-клиента)."""
    # Схема не зависит от значений настроек — подставляем заглушки.
    app = create_app(
        Settings(
            _env_file=None,
            app_env="dev",  # не prod: иначе валидатор потребует ключи капчи и Telegram
            database_url="postgresql+asyncpg://openapi@localhost/openapi",
            redis_url="redis://localhost",
            revalidate_secret="openapi-placeholder-secret",  # noqa: S106
            s3_bucket="openapi",
            s3_access_key="openapi",
            s3_secret_key="openapi-placeholder-secret",  # noqa: S106
        )
    )
    content = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    cli()
