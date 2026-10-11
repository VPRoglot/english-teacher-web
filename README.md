# Сайт репетитора по английскому

Персональный сайт репетитора: публичная страница с заявкой на пробное занятие, мини-CRM заявок и кабинеты родителя и ребёнка с расписанием и заметками к занятиям.

- Дизайн MVP: [docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md](docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md)
- Планы реализации: [docs/superpowers/plans/](docs/superpowers/plans/)

**Стек:** FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL 16 · Redis 7 · Taskiq (worker) · MinIO / S3 · Next.js 16 · TanStack Query · Tailwind + shadcn/ui · Docker Compose.

## Требования

- Docker Desktop (запущен — нужен и для стека, и для тестов backend)
- [uv](https://docs.astral.sh/uv/) и Python 3.12 (`uv python install 3.12`)
- Node.js ≥ 20.9 (в контейнерах и CI — 22) и pnpm (`corepack enable`)
- [just](https://just.systems/)

## Быстрый старт

```bash
cp .env.example .env          # Windows: copy .env.example .env
just dev                      # postgres, redis, minio, миграции, api на :8000 (hot reload), worker
just create-tutor you@example.com
just web                      # frontend на http://localhost:3000, /api проксируется на :8000
```

Проверка: `http://localhost:8000/api/health/ready` → `{"status":"ok",...}`, Swagger — `http://localhost:8000/api/docs`.

## Команды

| Команда | Что делает |
|---|---|
| `just dev` / `just down` / `just logs [service]` | dev-стек в Docker |
| `just dev-full` | то же + production-сборка frontend в контейнере на :3000 |
| `just restart <service>` | перезапустить сервис dev-стека; у worker нет hot reload — `just restart worker` после правки задач |
| `just migrate` | применить миграции Alembic |
| `just create-tutor <email>` | создать учётную запись репетитора (одна на систему) |
| `just api` | backend вне Docker; localhost-хосты — в `backend/.env` (см. `.env.example`) |
| `just worker` | worker задач вне Docker (нужен redis из `just dev`; после правок задач перезапустить) |
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
S3_ENDPOINT_URL=http://localhost:9000
```

## Контент сайта: лендинг, worker, MinIO

Тексты и фото публичной страницы репетитор правит в `/admin/site` (блоки `hero`, `about`, `services`, `reviews`, `faq`, `contacts`). Лендинг `/` рендерится на сервере из блоков, закешированных в Next под тегом `site-content`. Чтобы правка появилась без пересборки, backend сбрасывает этот кеш:

```
сохранение блока → задача в очереди (Redis) → worker → POST /api/revalidate → тег site-content
```

- **Порядок.** API ставит задачу только после `commit`, поэтому Next не успеет закешировать старые данные. Если Redis недоступен, блок всё равно сохраняется (ответ 200), а в лог пишется `site_revalidation_enqueue_failed`; тогда обновить кеш можно повторным сохранением блока.
- **Повторы.** Задача `site_content.revalidate_site` делает до 5 попыток; пауза между ними растёт и не превышает 60 с (пауза выдерживается внутри worker, `DelayedRetryMiddleware` в `backend/app/core/tasks.py`). Пока Next остановлен, в `just logs worker` видны повторы; после его запуска очередной повтор проходит.
- **Один `request_id`.** Задача наследует `request_id` запроса, который её поставил: в `just logs api` и `just logs worker` (события `task_started` / `task_finished`) он совпадает.
- **Worker и hot reload.** У api hot reload есть, у worker нет: после правки задач выполните `just restart worker`. Worker вне Docker — `just worker`.
- **Адрес Next для worker.** `REVALIDATE_URL` задаёт Docker Compose: в production `http://web:3000/api/revalidate`, в dev — `http://host.docker.internal:3000/api/revalidate`, потому что `just web` запускает Next на хосте.
- **Секрет.** `REVALIDATE_SECRET` должен быть **одинаковым у backend и web** (не короче 16 символов): worker отправляет его как `Authorization: Bearer ...`, Next сверяет. В dev значение уже совпадает в `.env` и `frontend/.env.development`; в production задайте случайную строку, например `openssl rand -hex 32`.

**Фото.** Загрузка в `/admin/site` проходит через backend: тип определяется по содержимому (только JPEG, PNG, WebP), размер не больше 5 МБ, EXIF удаляется, длинная сторона уменьшается до 2000 px. Файл кладётся в S3-совместимое хранилище по ключу `site/{uuid}.{jpg|png|webp}`, на странице он отдаётся по `/media/...`. Ограничение размера тела запроса до буферизации — задача nginx (план 7); приложение и само отсекает слишком большую загрузку до разбора multipart (`UploadLimitMiddleware`: 413 при `Content-Length` или потоке больше 5 МБ + 1 МиБ запаса) и дополнительно отклоняет файлы больше 5 МБ.

**MinIO в разработке.** `just dev` поднимает MinIO и одноразовый `minio-init`: он создаёт бакет (`S3_BUCKET`) и включает анонимное чтение, так фото отдаются на лендинге. Образы — Chainguard (`cgr.dev/chainguard/minio`, `cgr.dev/chainguard/minio-client`), потому что официальные образы minio недоступны для скачивания. Консоль: http://localhost:9001 (логин и пароль — `S3_ACCESS_KEY` и `S3_SECRET_KEY` из `.env`), S3 API — `http://localhost:9000`. В dev Next проксирует `/media` на MinIO (`MEDIA_PROXY_URL`), в production `/media` проксирует nginx. Вместо MinIO можно указать настоящий AWS S3: удалите строку `S3_ENDPOINT_URL` и задайте `S3_ADDRESSING_STYLE=virtual`.

**Переменные окружения.** Все описаны комментариями в `.env.example`. Контейнер `web` не читает `.env` целиком (в нём секреты backend): Compose передаёт ему только `API_INTERNAL_URL`, `SITE_URL` и `REVALIDATE_SECRET`, подставляя значения из `.env`.

| Где | Переменные |
|---|---|
| backend | `REVALIDATE_URL`, `REVALIDATE_SECRET`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_ADDRESSING_STYLE`, `MEDIA_PUBLIC_BASE_URL` |
| frontend | `API_INTERNAL_URL`, `SITE_URL`, `REVALIDATE_SECRET`, `MEDIA_PROXY_URL` (только dev) |

Next читает эти переменные во время запроса, поэтому `pnpm --dir frontend build` проходит без запущенного API.

**SEO.** `SITE_URL` (без завершающего `/`) определяет canonical, Open Graph, `robots.txt` и `sitemap.xml`. `robots.txt` закрывает `/admin`, `/cabinet`, `/invite`, `/reset`, `/login` и `/api`.

**Перед production** заполните в `/admin/site` поле `hero.name` (имя репетитора) и блок `contacts`: они попадают на страницу `/privacy` как имя и контакты оператора персональных данных. По умолчанию там заглушки из миграции.

## Тесты

- Backend: `just test-backend` — pytest поднимает PostgreSQL и Redis через testcontainers (нужен запущенный Docker), порог покрытия 85%.
- Frontend: `just test-frontend` — Vitest + Testing Library.
- После изменения API backend выполните `just gen-api` и закоммитьте результат — CI проверяет, что клиент актуален.
