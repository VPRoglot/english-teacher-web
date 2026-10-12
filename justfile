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

restart *args:
    {{compose}} restart {{args}}

migrate:
    {{compose}} run --rm migrate

create-tutor email:
    {{compose}} run --rm api python -m app.cli create-tutor --email {{email}}

# backend вне Docker (нужны postgres/redis из `just dev` и localhost-хосты в backend/.env)
api:
    uv --directory backend run uvicorn app.main:create_app --factory --reload --port 8000

# worker задач вне Docker (нужен redis из `just dev`; после правок задач перезапустить)
worker:
    uv --directory backend run taskiq worker app.worker:broker

# планировщик задач вне Docker (нужен redis из `just dev`; ровно один экземпляр)
scheduler:
    uv --directory backend run taskiq scheduler app.scheduler:scheduler

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

# Проверка prod-compose (docker-compose.yml + docker-compose.prod.yml) с infra/prod.env.example.
# base-compose читает env_file ../.env: без корневого .env скопируйте prod.env.example в .env.
prod-config:
    docker compose --env-file infra/prod.env.example -f infra/docker-compose.yml -f infra/docker-compose.prod.yml config -q

fmt:
    uv --directory backend run ruff check --fix .
    uv --directory backend run ruff format .
