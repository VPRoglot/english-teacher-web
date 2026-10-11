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

## Первый запуск: репетитор, семья, приглашение

Сквозной сценарий: от создания репетитора до входа ребёнка. Подходит и как ручная проверка после изменений в авторизации.

```bash
cp .env.example .env                           # Windows: copy .env.example .env
just dev                                       # postgres, redis, миграции, api на :8000
just create-tutor tutor@example.com            # спросит пароль (не короче 8 символов)
just web                                       # http://localhost:3000
```

Проверка стека: `http://localhost:8000/api/health/ready` → `{"status":"ok",...}`; `http://localhost:3000/login` открывается. Если схема БД устарела — `just migrate`.

1. Откройте `http://localhost:3000/login`, войдите репетитором — вас перебросит на `/admin`.
2. `/admin/families` → «Новая семья» → название «Тестовые» → откроется карточка семьи.
3. «Добавить ребёнка»: имя «Маша», уровень A2 — ребёнок появится в карточке.
4. «Создать ссылку-приглашение» → скопируйте URL.
5. Выйдите и откройте URL приглашения: заполните форму родителя (ФИО, телефон, email, пароль, согласие) — вы попадёте в `/cabinet`, где видна «Маша». В карточке семьи у репетитора появится «Последний вход» родителя.
6. `/cabinet/children` → выдайте Маше логин `masha.test` и пароль из 6+ символов.
7. Выйдите и войдите как `masha.test` — откроется `/cabinet`, в навигации нет пункта «Дети».
8. Под ребёнком откройте `http://localhost:3000/admin` — вас вернёт на `/cabinet`; запрос `GET /api/admin/families` отвечает 404.
9. Войдите репетитором и архивируйте семью: повторный вход родителя даёт «Неверный логин или пароль».
10. Шесть неверных попыток входа подряд с одним логином — сообщение о лимите попыток (лимит: 5 неудачных попыток за 15 минут на пару «логин + IP»).

В консоли браузера не должно быть ошибок, кроме ожидаемых 401/404 сетевых ответов.

**Про `backend/.env`.** `.env` в корне рассчитан на Docker Compose (хосты `postgres` и `redis`). Чтобы запускать backend вне Docker через `just api`, создайте `backend/.env` (в git не попадает) с localhost-переопределениями — см. комментарий в начале `.env.example`:

```
DATABASE_URL=postgresql+asyncpg://tutor:change-me@localhost:5432/tutor
REDIS_URL=redis://localhost:6379/0
```

## Тесты

- Backend: `just test-backend` — pytest поднимает PostgreSQL и Redis через testcontainers (нужен запущенный Docker), порог покрытия 85%.
- Frontend: `just test-frontend` — Vitest + Testing Library.
- После изменения API backend выполните `just gen-api` и закоммитьте результат — CI проверяет, что клиент актуален.
