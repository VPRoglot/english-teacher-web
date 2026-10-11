import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError

from app.auth.identity import normalize_email
from app.auth.service import create_tutor
from app.core.config import Settings, get_settings
from app.core.db import create_db_engine, create_sessionmaker
from app.core.errors import AppError
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
