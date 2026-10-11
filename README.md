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
- **Повторы.** Задача `site_content.revalidate_site` делает до 5 попыток всего (первая и до 4 повторов); пауза между ними растёт и не превышает 60 с (пауза выдерживается внутри worker, `DelayedRetryMiddleware` в `backend/app/core/tasks.py`). Пока Next остановлен, в `just logs worker` видны повторы; после его запуска очередной повтор проходит.
- **Один `request_id`.** Задача наследует `request_id` запроса, который её поставил: в `just logs api` и `just logs worker` (события `task_started` / `task_finished`) он совпадает.
- **Worker и hot reload.** У api hot reload есть, у worker нет: после правки задач выполните `just restart worker`. Worker вне Docker — `just worker`.
- **Адрес Next для worker.** `REVALIDATE_URL` задаёт Docker Compose: в production `http://web:3000/api/revalidate`, в dev — `http://host.docker.internal:3000/api/revalidate`, потому что `just web` запускает Next на хосте.
- **Секрет.** `REVALIDATE_SECRET` должен быть **одинаковым у backend и web** (не короче 16 символов): worker отправляет его как `Authorization: Bearer ...`, Next сверяет. В dev значение уже совпадает в `.env` и `frontend/.env.development`; в production задайте случайную строку, например `openssl rand -hex 32`.

**Фото.** Загрузка в `/admin/site` проходит через backend: тип определяется по содержимому (только JPEG, PNG, WebP), размер не больше 5 МБ, EXIF удаляется, длинная сторона уменьшается до 2000 px. Файл кладётся в S3-совместимое хранилище по ключу `site/{uuid}.{jpg|png|webp}`, на странице он отдаётся по `/media/...`. Ограничение размера тела запроса до буферизации — задача nginx (план 7); приложение и само отсекает слишком большую загрузку до разбора multipart (`UploadLimitMiddleware`: 413 при `Content-Length` или потоке больше 5 МБ + 1 МиБ запаса) и дополнительно отклоняет файлы больше 5 МБ.

**MinIO в разработке.** `just dev` поднимает MinIO и одноразовый `minio-init`: он создаёт бакет (`S3_BUCKET`) и включает анонимное чтение, так фото отдаются на лендинге. Образы — Chainguard (`cgr.dev/chainguard/minio`, `cgr.dev/chainguard/minio-client`), потому что официальные образы minio недоступны для скачивания. Консоль: http://localhost:9001 (логин и пароль — `S3_ACCESS_KEY` и `S3_SECRET_KEY` из `.env`), S3 API — `http://localhost:9000`. В dev Next проксирует `/media` на MinIO (`MEDIA_PROXY_URL`), в production `/media` проксирует nginx. Вместо MinIO можно указать настоящий AWS S3: удалите строку `S3_ENDPOINT_URL` и задайте `S3_ADDRESSING_STYLE=virtual`.

**Переменные окружения.** Все описаны комментариями в `.env.example`. Контейнер `web` не читает `.env` целиком (в нём секреты backend): Compose передаёт ему только `API_INTERNAL_URL`, `SITE_URL`, `REVALIDATE_SECRET` и `SMARTCAPTCHA_CLIENT_KEY`, подставляя значения из `.env` (последний необязателен).

| Где | Переменные |
|---|---|
| backend | `REVALIDATE_URL`, `REVALIDATE_SECRET`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_ADDRESSING_STYLE`, `MEDIA_PUBLIC_BASE_URL` |
| frontend | `API_INTERNAL_URL`, `SITE_URL`, `REVALIDATE_SECRET`, `SMARTCAPTCHA_CLIENT_KEY`, `MEDIA_PROXY_URL` (только dev) |

Переменные заявок и уведомлений (`SMARTCAPTCHA_*`, `TELEGRAM_*`, `TASK_ENQUEUE_TIMEOUT_SECONDS`) — в разделе «Заявки и уведомления».

Next читает эти переменные во время запроса, поэтому `pnpm --dir frontend build` проходит без запущенного API.

**SEO.** `SITE_URL` (без завершающего `/`) определяет canonical, Open Graph, `robots.txt` и `sitemap.xml`. `robots.txt` закрывает `/admin`, `/cabinet`, `/invite`, `/reset`, `/login` и `/api`.

**Перед production** заполните в `/admin/site` поле `hero.name` (имя репетитора) и блок `contacts`: они попадают на страницу `/privacy` как имя и контакты оператора персональных данных. По умолчанию там заглушки из миграции.

## Заявки и уведомления

Путь заявки: форма на `/` → `POST /api/public/leads` → задача `notifications.notify_new_lead` в очереди → worker → сообщение в Telegram репетитору. Заявка сохраняется в БД независимо от судьбы уведомления; репетитор ведёт её в `/admin/leads`.

**Форма.** Поля: родитель, ребёнок, возраст, телефон (маска), способ связи (Telegram, WhatsApp, телефон), ник в мессенджере, цель, удобное время. Обязательно согласие со ссылкой на `/privacy`. UTM-метки (`utm_source`, `utm_medium`, `utm_campaign`) берутся из URL, сохраняются в `sessionStorage` и уходят вместе с заявкой. Защита от спама:

- **Honeypot.** Скрытое поле `website`: если оно заполнено, API отвечает так же, как на настоящую заявку (`201 {"accepted": true}`), но ничего не сохраняет и задачу не ставит.
- **Rate limit.** 3 заявки в час с одного IP; четвёртая получает `429` с заголовком `Retry-After` и сообщением о лимите. Попытка учитывается до остальных проверок. За прокси IP берётся из `request.client`, проброс `X-Forwarded-For` настраивается отдельно.
- **Yandex SmartCaptcha** в невидимом режиме. Неверный токен — `400 captcha_failed`, ничего не сохраняется. Проверка работает по принципу fail-open (рекомендация Яндекса): если сервис капчи недоступен или ответил не 200, заявка проходит, а в лог пишется `captcha_unavailable`; honeypot и rate limit действуют всегда.

**Уведомление.** Сообщение уходит обычным текстом (без `parse_mode`) и содержит имя родителя и ребёнка, возраст, способ связи, телефон, цель, удобное время и ссылку `{PUBLIC_BASE_URL}/admin/leads/{id}`; длиннее 4096 символов обрезается. Задачу API ставит после `commit`; если Redis недоступен, заявка всё равно сохраняется (ответ `201`), а в лог пишется `lead_notification_enqueue_failed`. Таймаут постановки — `TASK_ENQUEUE_TIMEOUT_SECONDS` (по умолчанию 2 с). Повторы такие же, как у сброса кеша: до 5 попыток всего (первая и до 4 повторов) с нарастающей паузой до 60 с. Задача идемпотентна: после успешной отправки в заявке заполняется `notified_at`, и повторная доставка второго сообщения не шлёт. Как и для других задач, `request_id` в `just logs worker` (события `task_started` / `task_finished`) совпадает с `request_id` запроса `POST /api/public/leads`.

**Без ключей в dev.** Если `SMARTCAPTCHA_SERVER_KEY` не задан, капча на сервере отключена, а если не задан `SMARTCAPTCHA_CLIENT_KEY`, форма работает без неё. Если нет `TELEGRAM_BOT_TOKEN` или `TELEGRAM_CHAT_ID`, worker сообщение не шлёт, а пишет в лог `telegram_disabled` (задача при этом завершается успешно, `notified_at` заполняется). При `APP_ENV=prod` backend без `SMARTCAPTCHA_SERVER_KEY`, `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` не запустится.

| Переменная | Где | Назначение |
|---|---|---|
| `SMARTCAPTCHA_SERVER_KEY` | backend | серверный ключ SmartCaptcha; обязателен в prod |
| `SMARTCAPTCHA_CLIENT_KEY` | frontend | клиентский ключ; читается во время запроса; при `just web` — в `frontend/.env.development`, для контейнера `web` — в корневом `.env`; задаётся вместе с серверным |
| `TELEGRAM_BOT_TOKEN` | backend (worker) | токен бота; обязателен в prod |
| `TELEGRAM_CHAT_ID` | backend (worker) | чат, куда бот пишет; обязателен в prod |
| `TASK_ENQUEUE_TIMEOUT_SECONDS` | backend (api) | потолок постановки задачи в очередь, по умолчанию 2 |

**Где задавать ключи.** Серверные значения (`SMARTCAPTCHA_SERVER_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) — в корневой `.env`: их читают контейнеры api и worker. Клиентский ключ зависит от способа запуска frontend: при `just web` Next работает на хосте и читает `frontend/.env.development`, а не корневой `.env`, поэтому `SMARTCAPTCHA_CLIENT_KEY` пишется туда (после правки перезапустите `just web`). В корневой `.env` он нужен только для контейнера `web` (`just dev-full`, production).

**Ключи SmartCaptcha задаются парой.** Серверный ключ без клиентского даёт форму без капчи, и каждая заявка получает `400 captcha_failed` (нет токена — сервер отказывает). Клиентский ключ без серверного ничего не защищает: сервер капчу не проверяет. Задавайте оба или ни одного.

**После правки `.env` контейнеры нужно пересоздать.** `just restart` выполняет `docker compose restart`: контейнер сохраняет окружение, с которым был создан, и новый `.env` не подхватывает. Выполните `just dev` (это `up --build -d`, он пересоздаёт изменившиеся сервисы) или точечно `docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d worker api` (и `web` при `just dev-full`). `just restart` годится только после правки кода: он подхватывается из bind mount.

**Как создать бота и узнать `TELEGRAM_CHAT_ID`.**

1. В Telegram откройте [@BotFather](https://t.me/BotFather), выполните `/newbot`, задайте имя и username. BotFather пришлёт токен — это `TELEGRAM_BOT_TOKEN`.
2. Откройте диалог с созданным ботом и отправьте ему любое сообщение (бот не может писать первым). Для группы добавьте бота в группу и напишите в ней.
3. Откройте `https://api.telegram.org/bot<токен>/getUpdates` и найдите `message.chat.id`: это `TELEGRAM_CHAT_ID` (у групп число отрицательное). Для группы в ответе может быть только `my_chat_member` (добавление бота): id лежит в `my_chat_member.chat.id`.
4. Токен даёт полный доступ к боту: не публикуйте его и не коммитьте `.env`. Если токен утёк, выпустите новый через `/revoke` в BotFather.

**Где взять ключи SmartCaptcha.** В консоли [Yandex Cloud](https://console.yandex.cloud/) → SmartCaptcha → «Создать капчу» (форма использует невидимый режим; домен сайта добавьте в настройках капчи). В карточке капчи: «Ключ клиента» — `SMARTCAPTCHA_CLIENT_KEY`, «Ключ сервера» — `SMARTCAPTCHA_SERVER_KEY`.

**Админка заявок.** `/admin/leads`: список со статусами, фильтр по статусу, поиск и постраничный вывод; карточка `/admin/leads/{id}` с историей статусов. API: `GET /api/admin/leads`, `GET /api/admin/leads/{id}`, `PATCH /api/admin/leads/{id}`, `POST /api/admin/leads/{id}/convert`.

Статусы: «Новая» (`new`), «Связались» (`contacted`), «Пробное назначено» (`trial_scheduled`), «Стала учеником» (`converted`), «Отказ» (`rejected`). Переходы:

- `new` → `contacted`, `trial_scheduled`, `rejected`;
- `contacted` → `trial_scheduled`, `rejected`;
- `trial_scheduled` → `converted`, `rejected`, `contacted`;
- `rejected` → `contacted`;
- `converted` — конечный.

Вручную через `PATCH` выставляются только `contacted` и `rejected` (отказ требует причину, иначе `422`); недопустимый переход даёт `409 invalid_status_transition`. Каждый переход записывается в историю. «Конвертировать» создаёт в одной транзакции семью, ребёнка и ссылку-приглашение с предзаполненными ФИО и телефоном; повторная конвертация возвращает `409 lead_not_convertible`. Конвертировать можно только заявку в статусе `trial_scheduled`.

**Появится в плане 5.** Статус `trial_scheduled` и кнопка «Назначить пробное» (`POST /api/admin/leads/{id}/trial`) появятся вместе с расписанием: пробное занятие — это занятие, а таблица занятий создаётся в плане 5. Пока кнопка «Конвертировать» неактивна, а для ручной проверки статус выставляется SQL:

```bash
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.dev.yml exec postgres psql -U tutor -d tutor -c "UPDATE leads SET status = 'trial_scheduled' WHERE id = '<id заявки>'"
```

**Эксплуатация: очередь задач.** Брокер Taskiq хранит задачи в потоке Redis `taskiq` и читает их группой `taskiq`. Теперь группа создаётся с начала потока (`consumer_id="0"` в `backend/app/core/tasks.py`), чтобы задачи, поставленные API до первого запуска worker, не терялись. Если в окружении worker уже запускался раньше, группа `taskiq` там создана со старой позицией `$` (только новые сообщения) и существующую группу брокер не пересоздаёт. Один раз удалите её, затем перезапустите worker, и он создаст группу заново с начала потока:

```bash
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.dev.yml exec redis redis-cli XGROUP DESTROY taskiq taskiq
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.dev.yml restart worker
```

Сообщения ack-нутых задач из потока не удаляются (его длина ограничена примерно 10 000 записей), поэтому после пересоздания группы worker один раз повторно прогонит сохранившуюся историю потока. Это безопасно: задачи идемпотентны (сброс кеша лендинга и уведомление с `notified_at`). В production замените файлы `-f` на свои, а на новом окружении ничего делать не нужно.

## Тесты

- Backend: `just test-backend` — pytest поднимает PostgreSQL и Redis через testcontainers (нужен запущенный Docker), порог покрытия 85%.
- Frontend: `just test-frontend` — Vitest + Testing Library.
- После изменения API backend выполните `just gen-api` и закоммитьте результат — CI проверяет, что клиент актуален.
