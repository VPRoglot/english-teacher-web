# Сайт репетитора по английскому

Персональный сайт репетитора: публичная страница с заявкой на пробное занятие, мини-CRM заявок и кабинеты родителя и ребёнка с расписанием и заметками к занятиям.

- Дизайн MVP: [docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md](docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md)
- Планы реализации: [docs/superpowers/plans/](docs/superpowers/plans/)

**Стек:** FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL 16 · Redis 7 · Next.js 16 · TanStack Query · Tailwind + shadcn/ui · Docker Compose.

## Требования

- Docker Desktop (запущен — нужен и для стека, и для тестов backend)
- [uv](https://docs.astral.sh/uv/) и Python 3.12 (`uv python install 3.12`)
- Node.js ≥ 20.9 (в контейнерах и CI — 22) и pnpm (`corepack enable`)
- [just](https://just.systems/)

## Быстрый старт

```bash
cp .env.example .env          # Windows: copy .env.example .env
just dev                      # postgres, redis, миграции, api на :8000 (hot reload)
just create-tutor you@example.com
just web                      # frontend на http://localhost:3000, /api проксируется на :8000
```

Проверка: `http://localhost:8000/api/health/ready` → `{"status":"ok",...}`, Swagger — `http://localhost:8000/api/docs`.

## Команды

| Команда | Что делает |
|---|---|
| `just dev` / `just down` / `just logs [service]` | dev-стек в Docker |
| `just dev-full` | то же + production-сборка frontend в контейнере на :3000 |
| `just migrate` | применить миграции Alembic |
| `just create-tutor <email>` | создать учётную запись репетитора (одна на систему) |
| `just api` | backend вне Docker; localhost-хосты — в `backend/.env` (см. `.env.example`) |
| `just web` | Next.js dev-сервер |
| `just gen-api` | OpenAPI из backend → типизированный клиент `frontend/src/api/generated` |
| `just test` / `just test-backend` / `just test-frontend` | тесты |
| `just lint` / `just fmt` | линтеры и автоформатирование |

## Тесты

- Backend: `just test-backend` — pytest поднимает PostgreSQL и Redis через testcontainers (нужен запущенный Docker), порог покрытия 85%.
- Frontend: `just test-frontend` — Vitest + Testing Library.
- После изменения API backend выполните `just gen-api` и закоммитьте результат — CI проверяет, что клиент актуален.
