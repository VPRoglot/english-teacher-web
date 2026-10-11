set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Каждая строка рецепта — отдельная команда: без `&&` (PowerShell 5.1) и без `cd`.

compose := "docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.dev.yml"

# Поднять dev-стек: postgres, redis, migrate, api (hot reload)
dev:
    {{compose}} up --build -d

# То же + frontend в контейнере (production-сборка) на :3000
dev-full:
    {{compose}} --profile docker-web up --build -d

down:
    {{compose}} --profile docker-web down

logs *args:
    {{compose}} logs -f {{args}}

migrate:
    {{compose}} run --rm migrate

create-tutor email:
    {{compose}} run --rm api python -m app.cli create-tutor --email {{email}}

# backend вне Docker (нужны postgres/redis из `just dev` и localhost-хосты в backend/.env)
api:
    uv --directory backend run uvicorn app.main:create_app --factory --reload --port 8000

test-backend *args:
    uv --directory backend run pytest {{args}}

lint-backend:
    uv --directory backend run ruff check .
    uv --directory backend run ruff format --check .
    uv --directory backend run mypy

test-frontend:
    pnpm --dir frontend test

lint-frontend:
    pnpm --dir frontend lint
    pnpm --dir frontend typecheck

test: test-backend test-frontend

lint: lint-backend lint-frontend

# frontend на http://localhost:3000; /api проксируется на backend (frontend/.env.development)
web:
    pnpm --dir frontend dev

# OpenAPI из backend → frontend/openapi.json → типизированный клиент (orval)
gen-api:
    uv --directory backend run python -m app.cli export-openapi ../frontend/openapi.json
    pnpm --dir frontend gen:api

fmt:
    uv --directory backend run ruff check --fix .
    uv --directory backend run ruff format .
