# Веб-приложение репетитора по английскому — дизайн MVP

- **Дата:** 2026-10-11
- **Статус:** на согласовании
- **Автор:** Иван (разработчик) + Claude

---

## 1. Цель и контекст

### 1.1. Что строим и для кого

Персональный сайт **одного конкретного репетитора** по английскому языку (знакомый разработчика) с публичной страницей, приёмом заявок и личными кабинетами для семей учеников. Мультиарендность (несколько репетиторов, SaaS) не требуется.

Пользователи:

| Роль | Кто это | Что делает |
|---|---|---|
| `tutor` | Репетитор, единственный администратор | Ведёт заявки, семьи, расписание, заметки, редактирует публичную страницу |
| `parent` | Родитель ученика | Смотрит расписание и заметки по своим детям, запрашивает перенос/отмену |
| `child` | Ребёнок-ученик | Смотрит своё расписание и заметки, подключается к занятию |
| посетитель | Потенциальный клиент | Знакомится с репетитором, оставляет заявку на пробное занятие |

### 1.2. Критерии успеха MVP

1. Посетитель находит страницу репетитора (SEO), понимает предложение и оставляет заявку за ~1 минуту с телефона.
2. Репетитор узнаёт о новой заявке в Telegram в течение минуты и ведёт её по статусам до превращения в ученика.
3. Родитель и ребёнок в любой момент видят прошедшие и предстоящие занятия, ссылку на подключение и общие заметки.
4. Перенос/отмена занятия проходит через кабинет, а не через переписку в мессенджерах.
5. Репетитор сам редактирует контент публичной страницы без участия разработчика.
6. Система «сделана правильно»: типизация, тесты, CI/CD, бэкапы, мониторинг, соответствие 152-ФЗ.

### 1.3. Решения, принятые в ходе обсуждения

| Вопрос | Решение |
|---|---|
| Для кого | Один репетитор (вариант A) |
| Объём MVP | Публичная страница + заявка на пробное + мини-CRM заявок; кабинеты родителя/ребёнка с календарём прошедших/будущих занятий и заметками |
| Управление занятиями | Создаёт и меняет только репетитор (включая регулярные); родитель может запросить перенос/отмену с комментарием, репетитор подтверждает или отклоняет |
| Аккаунты | Репетитор создаёт семью и пересылает родителю ссылку-приглашение; у ребёнка свой вход по логину и паролю (без email), который задаёт репетитор или родитель. Взрослые ученики без родителя в MVP не поддерживаются |
| Заметки | Пишет только репетитор; две части: общая (видна семье) и приватная (видна только репетитору). Комментариев от семьи нет |
| Контент публичной страницы | Своя админка с фиксированным набором блоков, у каждого — форма редактирования |
| Уведомление о заявке | Сообщение в Telegram репетитору |
| Приглашения | Ссылка генерируется в админке, репетитор пересылает её сам; email-рассылки в MVP нет |
| Хостинг | Российский VPS, Docker Compose |
| Архитектура | FastAPI (API) + Next.js (публичная SSR-страница, кабинет, админка) |
| Reverse proxy | nginx + certbot |

### 1.4. Вне объёма MVP (но архитектура это допускает)

- Самозапись в свободные окна репетитора (слоты).
- Учёт абонементов и оплат, онлайн-оплата (ЮKassa). Статус `cancelled_late` уже заложен для будущих списаний.
- Домашние задания (выдача, загрузка ответа, проверка).
- Telegram-бот для родителей: напоминания о занятиях, уведомления о переносах.
- Комментарии семьи к заметкам, чат.
- Email-рассылки и восстановление пароля по email.
- Взрослые ученики без родителя.
- Оценки, тесты, система поощрений (бейджи, серии), мини-игры, словарь с интервальным повторением.
- Статистика (доход, посещаемость), библиотека материалов, ежемесячный отчёт родителю.
- Аналитика (Яндекс Метрика) и cookie-баннер.
- Мультиязычный интерфейс (только русский).

---

## 2. Архитектура

### 2.1. Репозиторий

Монорепозиторий:

```
english-teacher-web/
├── backend/      # FastAPI, Taskiq worker, Alembic
├── frontend/     # Next.js
├── infra/        # docker-compose.*.yml, nginx, скрипты бэкапа, README по серверу
└── docs/
```

### 2.2. Контейнеры (production, один VPS)

```
           ┌──────── nginx (443, TLS / certbot) ────────┐
           │  /api/*   → api:8000                        │
           │  /media/* → публичный бакет S3              │
           │  /*       → web:3000                        │
           └─────────────────────────────────────────────┘
 web (Next.js standalone) ──SSR fetch──► api (FastAPI/uvicorn)
                                          │      │
                                   postgres:16   redis:7 ◄── worker (Taskiq)
                                                                 │
                                                       Telegram Bot API
 migrate (одноразовый, alembic upgrade head)
 backup (cron: pg_dump → S3)
```

- Один домен: браузер обращается к `/api` через nginx, поэтому cookie сессии работают без CORS.
- Публичная страница рендерится на сервере: Next.js запрашивает `GET /api/public/site` по внутренней сети Docker и кеширует ответ с тегом `site-content`. После сохранения блока в админке backend ставит задачу, worker вызывает защищённый секретом `POST /api/revalidate` у Next, и страница обновляется за секунды.
- Кабинет и админка — клиентские страницы на TanStack Query; Next здесь работает как роутер и сервер статики, бизнес-логики в Node нет.

### 2.3. Стек

| Задача | Выбор |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async, asyncpg), Alembic, Pydantic v2, pydantic-settings |
| Фоновые задачи | Taskiq + брокер на Redis (+ taskiq scheduler для периодических задач) |
| БД | PostgreSQL 16 |
| Redis | Сессии, rate limit, брокер задач, кеш |
| Файлы | S3-совместимое хранилище провайдера (локально MinIO) |
| Аутентификация | Сессии в httpOnly-cookie (хранение в Redis), argon2id, CSRF double-submit |
| Антиспам | Honeypot + rate limit + Яндекс SmartCaptcha |
| Повторяющиеся события | RRULE (python-dateutil), `zoneinfo` |
| Frontend | Next.js (App Router), TypeScript, TanStack Query, Tailwind CSS, shadcn/ui, react-hook-form + zod, FullCalendar (только MIT-плагины), react-markdown |
| API-клиент | orval: генерация типов, zod-схем и хуков TanStack Query из OpenAPI |
| Python tooling | uv, ruff, mypy `--strict`, pytest, testcontainers, polyfactory |
| Frontend tooling | pnpm, ESLint, Vitest + Testing Library, Playwright |
| Инфраструктура | Docker Compose, nginx + certbot, GitHub Actions, GHCR |
| Наблюдаемость | structlog (JSON-логи), Sentry SDK (Sentry или self-hosted GlitchTip), внешний uptime-пинг |

### 2.4. Backend: модульный монолит

Каждый модуль — пакет со слоями `router → service → repository`, своими Pydantic-схемами и ORM-моделями. Модули общаются только через функции сервисов, а не через прямой доступ к таблицам друг друга.

| Модуль | Ответственность |
|---|---|
| `core` | Конфигурация, сессия БД, ошибки, rate limit, логирование, request-id, health-checks |
| `auth` | Вход/выход, сессии, приглашения, ссылки сброса пароля, смена пароля, CSRF |
| `families` | Семьи, профили родителей, дети и их учётные записи |
| `leads` | Заявки на пробное, статусы, история, конвертация в семью |
| `lessons` | Серии, занятия, заметки, запросы на перенос/отмену, настройки репетитора |
| `site_content` | Блоки публичной страницы, загрузка медиа, revalidate |
| `notifications` | Отправка в Telegram через worker (интерфейс `Notifier`) |

Будущие модули (`assessments`, `rewards`, `games`, `billing`, `homework`) подключаются как новые пакеты, опираясь на `families` и `lessons`.

### 2.5. Роли и права

- `tutor` — единственный, создаётся CLI-командой `create-tutor` при развёртывании. Регистрации через интерфейс нет.
- `parent` — создаётся только через приглашение.
- `child` — учётную запись создаёт репетитор или родитель этой семьи.
- Права проверяются на backend зависимостями FastAPI (`require_role(...)` + область доступа к семье). Проверки во frontend служат только для удобства.

---

## 3. Модель данных (PostgreSQL)

Общие правила: первичные ключи UUIDv7; у каждой таблицы есть `created_at` и `updated_at`; время хранится как `timestamptz` в UTC; данные учеников по умолчанию не удаляются физически, а архивируются через `archived_at`.

### 3.1. Пользователи и семьи

```
users            id, role (tutor|parent|child), email NULL UNIQUE, username NULL UNIQUE,
                 password_hash, is_active, last_login_at
                 CHECK: role IN (tutor, parent) → email NOT NULL
                 CHECK: role = child → username NOT NULL
families         id, name, tutor_comment, archived_at
parent_profiles  user_id PK → users, family_id → families, full_name, phone, consent_at
children         id, family_id → families, user_id NULL UNIQUE → users, full_name,
                 birth_year, english_level (A1|A2|B1|B2|C1), default_meeting_url, archived_at
invitations      id, token_hash UNIQUE, family_id → families, prefill_full_name NULL,
                 prefill_phone NULL, expires_at, used_at, revoked_at, created_by → users
password_resets  id, token_hash UNIQUE, user_id → users, expires_at, used_at, created_by → users
```

- Email хранится в нижнем регистре, username тоже приводится к нижнему регистру; уникальность проверяется после нормализации.
- В семье может быть несколько родителей.
- Профиль ребёнка (`children`) отделён от его учётной записи (`children.user_id`): ребёнка можно завести сразу, а логин выдать позже.
- Приглашение предназначено только для родителя. Новое приглашение семьи аннулирует предыдущие неиспользованные (`revoked_at`). Срок жизни 7 дней.
- Профиль родителя создаётся только при принятии приглашения. До этого ФИО и телефон из заявки хранятся в `invitations.prefill_*` и предзаполняют форму.
- Ссылка сброса пароля создаётся репетитором для любого родителя или ребёнка. Срок жизни 24 часа.

### 3.2. Заявки (мини-CRM)

```
leads               id, parent_name, child_name, child_age, phone,
                    contact_method (telegram|whatsapp|phone), messenger_handle NULL,
                    goal NULL, preferred_time NULL (свободный текст),
                    status (new|contacted|trial_scheduled|converted|rejected),
                    reject_reason NULL, tutor_comment NULL, family_id NULL → families,
                    consent_at, utm_source NULL, utm_medium NULL, utm_campaign NULL,
                    anonymized_at NULL
lead_status_history id, lead_id → leads, from_status NULL, to_status, comment NULL, changed_at
```

Допустимые переходы статуса:

```
new → contacted | trial_scheduled | rejected
contacted → trial_scheduled | rejected
trial_scheduled → converted | rejected | contacted
rejected → contacted            (вернуть в работу)
converted — конечный
```

Переход в `trial_scheduled` происходит при назначении пробного занятия, переход в `converted` — при конвертации. Каждый переход записывается в `lead_status_history`.

### 3.3. Занятия

```
tutor_settings   singleton (id = 1): timezone (по умолчанию Europe/Moscow),
                 cancel_policy_hours (по умолчанию 24)
lesson_series    id, child_id → children, rrule, local_start_time, duration_min,
                 meeting_url NULL, starts_on (date), ends_on NULL (date), archived_at
lessons          id, series_id NULL → lesson_series, child_id NULL → children,
                 lead_id NULL → leads, kind (regular|trial), starts_at, duration_min,
                 meeting_url NULL, is_detached (bool, default false),
                 status (scheduled|completed|cancelled|cancelled_late|no_show)
                 CHECK: ровно одно из child_id / lead_id NOT NULL
                 CHECK: kind = trial ↔ lead_id NOT NULL
                 UNIQUE (series_id, starts_at)
lesson_notes     lesson_id PK → lessons, shared_text (markdown), private_text (markdown)
change_requests  id, lesson_id → lessons, requested_by → users, type (reschedule|cancel),
                 proposed_text NULL, comment NULL,
                 status (pending|approved|rejected|withdrawn),
                 tutor_response NULL, resolved_at NULL
                 UNIQUE (lesson_id) WHERE status = 'pending'
```

**Регулярные занятия.**

- Серия хранит правило RRULE (например, `FREQ=WEEKLY;BYDAY=TU,FR`) и местное время начала в часовом поясе репетитора.
- Ежедневная задача worker материализует занятия на 8 недель вперёд. Местное время переводится в UTC отдельно для каждой даты через `zoneinfo`, поэтому смена летнего и зимнего времени не сдвигает занятия. Генерация идемпотентна благодаря `UNIQUE (series_id, starts_at)`.
- При создании серии занятия на 8 недель генерируются сразу, синхронно.
- Если репетитор вручную меняет время одного занятия серии, оно получает `is_detached = true`.
- Правка серии со `scope=this_and_following` от выбранной даты меняет параметры серии и перегенерирует будущие занятия в статусе `scheduled` без `is_detached`. Прошедшие, отмеченные и отсоединённые занятия не трогаются. Технически серия разделяется: у старой выставляется `ends_on`, создаётся новая серия.
- Архивирование серии удаляет её будущие занятия в статусе `scheduled` (кроме `is_detached`) и прекращает генерацию.
- Удалять из БД разрешено только будущие занятия в статусе `scheduled`, по которым нет запросов. Всё остальное меняет статус, а не удаляется.

**Пробное занятие** — это запись в `lessons` с `kind = trial` и `lead_id`. Оно отображается в календаре репетитора. При конвертации заявки пробное занятие остаётся привязанным к заявке и не переносится в кабинет семьи.

**Прошедшие и предстоящие занятия** различаются по `starts_at` относительно текущего момента. Прошедшее занятие в статусе `scheduled` показывается репетитору как «нужно отметить».

**Поздняя отмена.** Отмена признаётся поздней, если запрос подан (или репетитор отменяет без запроса и явно выбирает этот вариант) менее чем за `cancel_policy_hours` часов до `starts_at`. Такое занятие получает статус `cancelled_late`; в будущем это основание для списания из абонемента.

**Приватная заметка** лежит в отдельной таблице `lesson_notes`. Ответы для семьи строятся из схем, в которых `private_text` нет.

### 3.4. Публичная страница

```
site_blocks  key PK (hero|about|services|reviews|faq|contacts), data JSONB, updated_at
media        id, s3_key, content_type, size_bytes, width, height
```

Каждый блок проверяется своей Pydantic-схемой. Начальный набор полей:

| Блок | Поля |
|---|---|
| `hero` | `title`, `subtitle`, `photo_media_id`, `cta_text` |
| `about` | `text` (markdown), `photo_media_id NULL`, `credentials: [str]` (образование, сертификаты, опыт) |
| `services` | `items: [{title, description, duration_min, price_rub, format}]` |
| `reviews` | `items: [{author, text, child_age NULL, photo_media_id NULL}]` |
| `faq` | `items: [{question, answer}]` |
| `contacts` | `telegram NULL`, `whatsapp NULL`, `phone NULL`, `email NULL`, `working_hours_text NULL` |

Начальные блоки с заглушками создаются миграцией данных.

---

## 4. API

Все пути начинаются с `/api`. OpenAPI-схема — источник истины для генерации frontend-клиента.

### 4.1. Публичные эндпоинты

```
GET  /public/site            все блоки публичной страницы (для SSR)
POST /public/leads           заявка; honeypot + SmartCaptcha + rate limit 3/час на IP
GET  /health                 живость процесса
GET  /health/ready           доступность БД и Redis
```

### 4.2. Аутентификация

```
POST /auth/login                        {login, password} → cookie сессии
POST /auth/logout
GET  /auth/me                           роль, профиль, семья, дети (для parent)
GET  /auth/csrf                         выдать CSRF-cookie
GET  /auth/invitations/{token}          проверить приглашение: имя семьи, срок
POST /auth/invitations/{token}/accept   {email, password, full_name, phone, consent: true} → аккаунт parent + вход
GET  /auth/password-resets/{token}      проверить ссылку сброса
POST /auth/password-resets/{token}      {password} → новый пароль, все сессии пользователя удалены
POST /auth/password                     {current_password, new_password}
```

`login` — это email (для родителя и репетитора) или username (для ребёнка). Поиск идёт по обоим полям после нормализации.

### 4.3. Кабинет (parent / child)

```
GET    /me/children                          (parent) дети своей семьи
POST   /me/children/{id}/account             (parent) создать или сменить логин и пароль ребёнка
GET    /me/lessons?from=&to=&child_id=       занятия в диапазоне; child видит только свои
GET    /me/lessons/{id}                      занятие + общая заметка + активный запрос
POST   /me/lessons/{id}/change-requests      (parent) {type, proposed_text?, comment?}
DELETE /me/change-requests/{id}              (parent) отозвать запрос, пока он pending
```

Запрос на перенос или отмену можно подать только для будущего занятия в статусе `scheduled`.

### 4.4. Админка (tutor)

```
GET    /admin/dashboard                       новые заявки, pending-запросы, занятия «нужно отметить», занятия сегодня
GET    /admin/leads?status=&q=                список с фильтром и поиском
GET    /admin/leads/{id}                      заявка + история статусов
PATCH  /admin/leads/{id}                      статус (по правилам переходов), tutor_comment, reject_reason
POST   /admin/leads/{id}/trial                {starts_at, duration_min, meeting_url?} → пробное занятие
POST   /admin/leads/{id}/convert              {family_name, child: {...}, parent: {...}} → семья + ссылка-приглашение
GET    /admin/families?q=&archived=
POST   /admin/families
GET    /admin/families/{id}                   семья, родители, дети, серии
PATCH  /admin/families/{id}                   в т.ч. архивирование
POST   /admin/families/{id}/invitations       → новая ссылка (старые аннулируются)
POST   /admin/families/{id}/children
PATCH  /admin/children/{id}
POST   /admin/children/{id}/account           создать или сменить логин и пароль ребёнка
POST   /admin/users/{id}/reset-link           → ссылка сброса пароля
PATCH  /admin/users/{id}                      is_active
GET    /admin/series?child_id=
POST   /admin/series                          → серия + занятия на 8 недель
PATCH  /admin/series/{id}?scope=this_and_following&from=
DELETE /admin/series/{id}                     архивирование серии
GET    /admin/lessons?from=&to=&child_id=     календарь репетитора (включая пробные)
POST   /admin/lessons                         разовое занятие
GET    /admin/lessons/{id}
PATCH  /admin/lessons/{id}                    время (→ is_detached), длительность, ссылка, статус
DELETE /admin/lessons/{id}                    только будущее scheduled без запросов
PUT    /admin/lessons/{id}/notes              {shared_text, private_text}
GET    /admin/change-requests?status=
POST   /admin/change-requests/{id}/approve    {new_starts_at?}  (обязателен для reschedule)
POST   /admin/change-requests/{id}/reject     {tutor_response}
GET    /admin/site-blocks
GET    /admin/site-blocks/{key}
PUT    /admin/site-blocks/{key}               проверка схемой блока → revalidate
POST   /admin/media                           jpeg/png/webp, ≤ 5 МБ
GET    /admin/settings
PUT    /admin/settings
```

Создание и перенос занятия возвращают в поле `warnings` предупреждение о пересечении по времени с другим занятием репетитора. Это не запрет.

### 4.5. Ключевые сценарии

1. **Заявка.** Форма → `POST /public/leads` → проверка honeypot, капчи и rate limit → сохранение заявки с `consent_at` и UTM → ответ `201` → задача Taskiq «уведомить репетитора в Telegram» (имя, возраст ребёнка, способ связи, ссылка на заявку в админке). При ошибке Telegram задача повторяется с нарастающей паузой, до 5 попыток. Заявка сохранена независимо от этого.
2. **Пробное занятие.** Репетитор в карточке заявки назначает пробное: создаётся `lesson(kind = trial)`, статус заявки переходит в `trial_scheduled`.
3. **Конвертация.** В одной транзакции: семья + ребёнок + приглашение с `prefill_full_name` и `prefill_phone` из заявки. Заявка переходит в `converted`, в `leads.family_id` записывается семья. Репетитор получает ссылку и кнопку «Скопировать».
4. **Принятие приглашения.** Родитель открывает `/invite/{token}`, видит имя семьи, вводит email, пароль, ФИО и телефон (ФИО и телефон предзаполнены) и отмечает согласие на обработку данных. Создаются `user(role = parent)` и `parent_profile` с `consent_at`, приглашение гасится, родитель сразу входит в систему.
5. **Перенос или отмена.**
   - Родитель открывает занятие и выбирает «Запросить отмену» или «Запросить перенос».
   - Если до начала меньше `cancel_policy_hours`, интерфейс заранее предупреждает, что отмена будет засчитана как проведённое занятие.
   - Создаётся `change_request(pending)`, репетитор получает уведомление в Telegram.
   - Одобрение отмены: статус занятия становится `cancelled` или `cancelled_late` в зависимости от времени подачи запроса.
   - Одобрение переноса: репетитор указывает `new_starts_at`, занятие получает новое время и `is_detached = true`.
   - Отклонение: обязателен `tutor_response`, его видит родитель.
   - Одобрение выполняется в транзакции с `SELECT … FOR UPDATE` по запросу и занятию.
6. **Правка контента.** `PUT /admin/site-blocks/{key}` → сохранение → задача revalidate → публичная страница обновлена.

### 4.6. Формат ошибок

```json
{"error": {"code": "lesson_not_found", "message": "Занятие не найдено", "details": {}}}
```

Коды стабильны, и frontend опирается на `code`. Ошибки валидации Pydantic отдаются с HTTP-статусом 422, кодом `validation_error` и списком полей в `details`. Непредвиденные ошибки отдаются как `500` с кодом `internal_error` и `request_id`.

---

## 5. Frontend (Next.js)

### 5.1. Страницы

```
Публичные (SSR)
/                       лендинг: hero → о себе → услуги и цены → отзывы → FAQ → контакты,
                        форма «Записаться на пробное» (#trial, кнопка в шапке)
/privacy                политика обработки персональных данных
/login                  вход
/invite/[token]         принятие приглашения
/reset/[token]          установка нового пароля

Кабинет (parent / child)
/cabinet                ближайшее занятие (карточка + «Подключиться»), предстоящие, последние заметки
/cabinet/calendar       месяц/неделя на десктопе, список на мобильном
/cabinet/lessons/[id]   детали, общая заметка, статус запроса, «Перенос/отмена» (parent)
/cabinet/children       (parent) дети, выдача и смена логина ребёнку
/cabinet/settings       смена пароля

Админка (tutor)
/admin                  дашборд
/admin/leads            таблица заявок с фильтром по статусу и поиском
/admin/leads/[id]       карточка заявки, история, «Назначить пробное», «Конвертировать»
/admin/calendar         неделя/день; клик по пустому месту → разовое занятие или серия
/admin/lessons/[id]     статус занятия, редактор общей и приватной заметки
/admin/families         список семей
/admin/families/[id]    родители, дети, серии, приглашения, ссылки сброса
/admin/requests         очередь запросов на перенос/отмену
/admin/site             редакторы блоков лендинга, загрузка фото, «Открыть сайт»
/admin/settings         часовой пояс, порог поздней отмены
```

### 5.2. Решения

- **Переключатель ребёнка** в шапке кабинета, если детей несколько. Выбор хранится в параметре URL `?child=`.
- **Мобильная версия в приоритете** для публичной страницы и кабинета. Админка адаптивная, основной сценарий — ноутбук.
- **Календарь:** FullCalendar, плагины `daygrid`, `timegrid`, `list`, `interaction` (лицензия MIT).
- **Отображение времени:** все даты показываются в часовом поясе репетитора (`tutor_settings.timezone`). Пояс указывается рядом со временем, если он отличается от пояса браузера.
- **API-клиент:** orval генерирует его из OpenAPI. Сгенерированный код коммитится, CI проверяет, что он совпадает со свежей генерацией.
- **Состояние:** серверные данные хранятся только в TanStack Query, формы — в react-hook-form со сгенерированными zod-схемами. Глобального хранилища нет.
- **Доступ:** middleware в Next проверяет наличие cookie сессии и перенаправляет на `/login`. После входа пользователь попадает в зону своей роли. Ответы `401` и `403` обрабатывает общий обработчик клиента.
- **Заметки:** Markdown, в админке редактор-textarea с предпросмотром, отрисовка через react-markdown без сырого HTML.
- **SEO:** `generateMetadata`, OpenGraph, JSON-LD (`Person`, `Service`), `sitemap.xml`, `robots.txt` (зоны `/cabinet`, `/admin`, `/invite`, `/reset` закрыты от индексации).
- **Форма заявки:** поля по модели `leads`, маска телефона, обязательное согласие со ссылкой на `/privacy`. UTM-метки берутся из URL, сохраняются в `sessionStorage` и передаются вместе с заявкой. Есть скрытое поле honeypot и SmartCaptcha (невидимый режим).
- **UI:** Tailwind + shadcn/ui, интерфейс только на русском.

---

## 6. Безопасность и надёжность

### 6.1. Аутентификация и сессии

- **Пароли:** argon2id. Минимальная длина 8 символов и проверка по списку распространённых паролей; для учётной записи ребёнка минимум 6 символов.
- **Сессия:** случайный 256-битный идентификатор в cookie `HttpOnly; Secure; SameSite=Lax`. В Redis хранится `session:{sha256(id)} → {user_id, role, created_at}` с плавающим сроком жизни: 30 дней для parent и child, 7 дней для tutor. Индекс `user_sessions:{user_id}` позволяет удалить все сессии пользователя.
- **Ротация:** сессия пересоздаётся при входе. При смене пароля, сбросе пароля или деактивации пользователя все его сессии удаляются. `is_active` проверяется на каждом запросе.
- **CSRF:** токен по схеме double-submit (cookie + заголовок `X-CSRF-Token`) для всех изменяющих запросов, плюс `SameSite=Lax`.
- **Защита от перебора** (rate limit в Redis): 5 неудачных попыток входа за 15 минут на пару «логин + IP» и 30 на один IP. Ответ на неудачный вход одинаков, существует логин или нет.
- **Одноразовые токены** (приглашения, сброс пароля): 32 случайных байта в URL-safe base64. В БД хранится только SHA-256, токен гасится после использования.

### 6.2. Авторизация

- Зависимость `family_scope` вычисляет множество доступных `child_id`: у родителя это все дети его семьи (кроме архивных), у ребёнка — он сам. Функции репозитория для кабинета принимают это множество обязательным параметром.
- Обращение к объекту вне своей области возвращает `404`.
- Схемы ответа для семьи (`LessonForFamily`, `NoteForFamily`) не содержат `private_text` и прочих полей, предназначенных только репетитору.
- Все `/admin/*` требуют `role = tutor` и для остальных ролей отвечают `404`.

### 6.3. Входные данные, файлы, заголовки, секреты

- Все входные данные проходят через Pydantic. Markdown отрисовывается без HTML.
- **Загрузка файлов:** тип определяется по содержимому (Pillow), а не по расширению; разрешены только jpeg, png и webp. EXIF удаляется, длинная сторона уменьшается до 2000 px. Файл сохраняется в S3 под именем-UUID.
- **nginx:** HSTS, CSP, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `client_max_body_size 6m`.
- **Секреты** задаются только через переменные окружения и `.env` на сервере. В репозитории лежит `.env.example`. pydantic-settings завершает запуск с ошибкой, если обязательной переменной нет.

### 6.4. 152-ФЗ

- Данные хранятся на сервере в РФ.
- Страница `/privacy`, обязательное согласие в форме заявки и при принятии приглашения; время согласия сохраняется.
- CLI-команда `purge-family <id>` физически удаляет семью и все связанные данные по запросу родителя.
- Периодическая задача обезличивает заявки в статусе `rejected` старше 12 месяцев: персональные поля заменяются, выставляется `anonymized_at`.

### 6.5. Ошибки и надёжность

- Доменные исключения (`NotFound`, `Conflict`, `PermissionDenied`, `ValidationFailed`) отображаются в единый формат ошибки (п. 4.6).
- **Сквозной идентификатор:** заголовок `X-Request-ID` проходит через nginx, api и worker (передаётся в метках задачи). Логи пишутся в JSON через structlog.
- **Защита от гонок:**
  - частичный уникальный индекс гарантирует один `pending`-запрос на занятие;
  - одобрение запроса выполняется под `SELECT … FOR UPDATE`;
  - генерация занятий идемпотентна.
- **Фоновые задачи** идемпотентны и повторяются с нарастающей паузой. Если worker недоступен, бизнес-данные не теряются, страдают только уведомления.
- **Бэкапы:** ежедневный `pg_dump` в S3, хранятся 14 дневных и 6 месячных копий. Процедура восстановления описана в `infra/README.md` и проверяется в CI на тестовой базе.
- **Health-checks:** `/api/health` и `/api/health/ready` используются в healthcheck Docker. Политика перезапуска контейнеров — `unless-stopped`.
- **Мониторинг:** Sentry SDK в api, worker и web, внешний uptime-пинг с оповещением в Telegram.

---

## 7. Тестирование

### 7.1. Backend (pytest)

- **Unit-тесты:**
  - генерация занятий из RRULE (переходы на летнее и зимнее время, `ends_on`, идемпотентность, `is_detached`, разделение серии);
  - расчёт поздней отмены;
  - переходы статусов заявки;
  - проверка схем блоков публичной страницы.
- **Интеграционные тесты:** API через `httpx.AsyncClient` на настоящих PostgreSQL и Redis (testcontainers), каждый тест в транзакции с откатом, данные из фабрик polyfactory.
- **Отдельный набор тестов на права доступа**, параметризованный по ролям:
  - родитель семьи A не видит занятия семьи B;
  - ребёнок не видит занятия брата или сестры;
  - `private_text` отсутствует во всех ответах для семьи;
  - ребёнок не может создать запрос на перенос или отмену;
  - все `/admin/*` для не-репетитора отвечают `404`.
- **Миграции:** в CI выполняется `upgrade head → downgrade base → upgrade head` и проверяется, что autogenerate не находит отличий между моделями и схемой БД.
- **Внешние зависимости** (Telegram, SmartCaptcha, revalidate) скрыты за интерфейсами, в тестах их заменяют фейки. S3 тестируется на MinIO.
- **Покрытие:** не ниже 85% для `backend/app`.

### 7.2. Frontend

- **Vitest + Testing Library:** форма заявки (валидация, маска, согласие), переключатель ребёнка, предупреждение о поздней отмене, формы редакторов блоков.
- **Playwright (e2e)** на полном стеке в docker-compose с тестовыми данными:
  1. Посетитель отправляет заявку, она появляется в админке.
  2. Репетитор назначает пробное и конвертирует заявку; родитель принимает приглашение и видит кабинет.
  3. Репетитор создаёт серию; родитель видит занятия в календаре.
  4. Родитель запрашивает перенос; репетитор одобряет; в кабинете новое время.
  5. Репетитор пишет заметку; родитель видит общую часть и не видит приватную.
  6. Репетитор правит блок лендинга; изменение видно на публичной странице.
  7. Родитель выдаёт ребёнку логин; ребёнок входит и видит только своё расписание.

---

## 8. Окружения, CI/CD, развёртывание

### 8.1. Docker

- `infra/docker-compose.yml` — базовое описание сервисов.
- `infra/docker-compose.dev.yml` — горячая перезагрузка, MinIO, открытые порты БД и Redis.
- `infra/docker-compose.prod.yml` — nginx + certbot, ограничения ресурсов, контейнер `backup`, наружу открыты только 80 и 443.
- **Образы:**
  - backend: многоэтапная сборка на `python:3.12-slim` + uv, запуск не от root;
  - frontend: Next `output: "standalone"` на `node:22-alpine`.
- Одноразовый сервис `migrate` выполняет `alembic upgrade head` до старта `api` и `worker`.
- **Корневой `justfile`:** `dev`, `test`, `lint`, `gen-api`, `migrate`, `create-tutor`, `e2e`.

### 8.2. CI (GitHub Actions, каждый PR)

1. **Backend:** `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` с покрытием, проверка миграций.
2. **Frontend:** `eslint`, `tsc --noEmit`, `vitest`, проверка, что повторный `gen:api` не даёт изменений.
3. **E2E:** сборка образов, `docker compose up`, Playwright; трассы и скриншоты сохраняются как артефакты при падении.

### 8.3. CD (merge в `main`)

1. Сборка образов с тегами `sha-<commit>` и `latest`, отправка в GHCR.
2. Подключение к VPS по SSH: `docker compose pull`, затем `migrate`, затем `up -d`.
3. Smoke-проверка `/api/health/ready` и `/`. При неудаче откат на предыдущий тег, сохранённый в `.env` на сервере (`IMAGE_TAG`).

### 8.4. Сервер

`infra/README.md` описывает:
- пользователя без root и вход в SSH только по ключу;
- ufw (22, 80, 443), fail2ban, автоматические обновления безопасности;
- получение и автопродление сертификатов certbot;
- первичное развёртывание (`create-tutor`, начальные блоки контента);
- восстановление из бэкапа.

---

## 9. Порядок реализации MVP

1. **Каркас:** монорепозиторий, docker-compose (dev), `core` (конфигурация, БД, ошибки, логирование, health-checks), CLI `create-tutor`, CI для линтеров и тестов.
2. **`auth` + `families`:** вход и выход, сессии, CSRF, rate limit, приглашения, ссылки сброса, учётные записи детей; страницы `/login`, `/invite`, `/reset`; базовый каркас кабинета и админки.
3. **`site_content` + лендинг:** блоки, медиа, SSR, revalidate, `/privacy`, SEO.
4. **`leads` + `notifications`:** форма заявки, антиспам, Telegram-уведомление, мини-CRM в админке (список, карточка, статусы, конвертация).
5. **`lessons`:** настройки репетитора, серии и материализация, разовые и пробные занятия, календари в админке и кабинете, заметки.
6. **Запросы на перенос и отмену:** кабинет, очередь в админке, уведомления, дашборд.
7. **Production:** docker-compose (prod), nginx + certbot, CD, бэкапы, мониторинг, обезличивание заявок, `purge-family`, e2e-набор целиком.

---

## 10. Направления развития после MVP

Не проектируются здесь; каждое пройдёт отдельный цикл дизайн → план → реализация.

- **Telegram-бот для родителей:** привязка аккаунта, напоминания за 24 и за 1 час, уведомления о переносах, заметках и решениях по запросам.
- **Абонементы и оплаты:** пакеты занятий, баланс, списание за `completed` и `cancelled_late`, онлайн-оплата.
- **Домашние задания:** выдача, загрузка ответа, проверка с комментарием.
- **Учебный контент:** библиотека материалов, тесты и оценки.
- **Геймификация:** бейджи, серии дней подряд, баллы, мини-игры, словарь с интервальным повторением.
- **Самозапись** в свободные окна.
- **Аналитика для репетитора:** доход, посещаемость, конверсия заявок по источникам (UTM уже собираются).
- **Ежемесячный отчёт родителю.**
