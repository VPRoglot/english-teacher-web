set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Каждая строка рецепта — отдельная команда: без `&&` (PowerShell 5.1) и без `cd`.

compose := "docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.dev.yml"

# Поднять dev-стек: postgres, redis, migrate, api (hot reload)
dev:
    {{compose}} up --build -d

down:
    {{compose}} down

logs *args:
    {{compose}} logs -f {{args}}

migrate:
    {{compose}} run --rm migrate

create-tutor email:
    {{compose}} run --rm api python -m app.cli create-tutor --email {{email}}

# backend вне Docker (нужны postgres/redis из `just dev` и localhost-хосты в .env)
api:
    uv --directory backend run uvicorn app.main:create_app --factory --reload --port 8000

test-backend *args:
    uv --directory backend run pytest {{args}}

lint-backend:
    uv --directory backend run ruff check .
    uv --directory backend run ruff format --check .
    uv --directory backend run mypy

fmt:
    uv --directory backend run ruff check --fix .
    uv --directory backend run ruff format .
