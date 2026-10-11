# План 4 из 7: `leads` + `notifications` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Посетитель оставляет заявку на пробное занятие с телефона за минуту. Заявка защищена honeypot, Яндекс SmartCaptcha и rate limit. Репетитор узнаёт о ней в Telegram и ведёт её в мини-CRM админки: список, карточка, статусы, конвертация в семью со ссылкой-приглашением.

**Architecture:**
- **Backend.** Два новых модуля:
  - `app/leads` — модели `leads` и `lead_status_history`, чистая таблица переходов статусов, публичный и админ-роутеры;
  - `app/notifications` — интерфейс `Notifier`, `TelegramNotifier` (Bot API) и задача Taskiq `notifications.notify_new_lead`.
- **Задача уведомления.** Worker сам читает заявку из БД (он получает sessionmaker) и помечает `notified_at`. Повторная доставка той же задачи не шлёт второе сообщение.
- **Капча** спрятана за интерфейсом `CaptchaVerifier`.
- **Доработки очереди из плана 3** — первая задача плана.
- **Frontend.**
  - Форма заявки — клиентский компонент в секции `#trial` лендинга.
  - Мини-CRM — клиентские страницы `/admin/leads` и `/admin/leads/[id]` на сгенерированных orval-хуках.

**Tech Stack:**
- Backend: как в плане 3, без новых зависимостей; httpx уже есть.
- Frontend: плюс `@yandex/smart-captcha` (React-компонент невидимой капчи).

**Spec:** `docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md` — используются разделы:
- 2.4 (`leads`, `notifications`);
- 3.2;
- 4.1 (`POST /public/leads`), 4.4 (`/admin/leads*`, кроме `/trial`), 4.5 п.1 и п.3;
- 5.1 (`/`, `#trial`, `/admin/leads`, `/admin/leads/[id]`), 5.2 (форма заявки);
- 6.4 (согласие), 6.5;
- 7.1 (переходы статусов), 7.2 (форма заявки);
- 9 п.4.

**Предыдущие планы:** 1–3 выполнены, код в `main`. Отложенное из плана 3 описано в `docs/superpowers/ledgers/2026-10-11-03-site-content.md` (строки `Ruling: deferred to plan 4 Task 1`).

**Уточнения спеки, принятые в этом плане:**
1. **`POST /admin/leads/{id}/trial` переносится в план 5.** Пробное занятие — это `lesson(kind = trial)`, а таблица занятий появляется в плане 5. Спека разрешает `converted` только из `trial_scheduled`, поэтому в плане 4 конвертация проверяется тестами, где статус выставлен напрямую. В UI кнопка «Конвертировать» до назначения пробного неактивна и сопровождается подсказкой.
2. **Ручные переходы через `PATCH`** — только в `contacted` и `rejected`, в пределах таблицы переходов спеки. `trial_scheduled` выставляет назначение пробного (план 5), `converted` — конвертация.
3. **В `leads` добавлено поле `notified_at timestamptz NULL`.** Оно делает задачу уведомления идемпотентной (спека 6.5: «Фоновые задачи идемпотентны»).
4. **В `lead_status_history` есть только `changed_at`, без `updated_at`.** Строки истории неизменяемы.
5. **Публичный ответ на заявку — `201 {"accepted": true}`.** Он одинаков для настоящей заявки и для сработавшего honeypot, чтобы бот не отличил одно от другого.
6. **SmartCaptcha работает по принципу fail-open** (рекомендация Яндекса). Ответ `status != "ok"` — отказ. Сетевая ошибка или HTTP не 200 — пропуск с предупреждением в логе. Honeypot и rate limit действуют всегда.

## Global Constraints

- **Всё из планов 1–3 действует:**
  - Python 3.12, префикс `/api`, UUIDv7, `timestamptz` в UTC;
  - единый формат ошибок, русские тексты;
  - ruff, mypy strict, eslint, tsc; покрытие ≥ 85%;
  - сессия БД только через `DbSession`;
  - после изменения API — `just gen-api` и коммит `frontend/openapi.json` + `frontend/src/api/generated/**`;
  - имена обработчиков = operationId, роутеры импортируют сервисы модулем;
  - `/admin/*` для не-репетитора → 404, без сессии → 401;
  - задача ставится в очередь только после `commit`; ошибка постановки логируется и не ломает ответ;
  - коммиты заканчиваются строкой `Co-Authored-By: <модель> <noreply@anthropic.com>`.
- **Поля заявки** (спека 3.2): `parent_name`, `child_name`, `child_age`, `phone`, `contact_method (telegram|whatsapp|phone)`, `messenger_handle NULL`, `goal NULL`, `preferred_time NULL` (свободный текст), `status (new|contacted|trial_scheduled|converted|rejected)`, `reject_reason NULL`, `tutor_comment NULL`, `family_id NULL → families`, `consent_at`, `utm_source NULL`, `utm_medium NULL`, `utm_campaign NULL`, `anonymized_at NULL`.
- **Переходы статуса** (спека 3.2, дословно):
  - `new → contacted | trial_scheduled | rejected`
  - `contacted → trial_scheduled | rejected`
  - `trial_scheduled → converted | rejected | contacted`
  - `rejected → contacted`
  - `converted` — конечный
  
  Каждый переход записывается в `lead_status_history`. Создание заявки пишет строку `NULL → new`.
- **`POST /public/leads`:** honeypot + SmartCaptcha + rate limit 3/час на IP. Сохранение с `consent_at` и UTM, ответ `201`, затем задача «уведомить репетитора в Telegram». Заявка сохранена независимо от судьбы уведомления.
- **Telegram-сообщение** содержит имя, возраст ребёнка, способ связи и ссылку на заявку в админке (`{PUBLIC_BASE_URL}/admin/leads/{id}`). Повторы — до 5 попыток с нарастающей паузой (уже в `DelayedRetryMiddleware`).
- **Конвертация** выполняется в одной транзакции: семья + ребёнок + приглашение с `prefill_full_name` и `prefill_phone`. Заявка переходит в `converted`, в `leads.family_id` записывается семья. Репетитор получает ссылку и кнопку «Скопировать».
- **Форма** (спека 5.2):
  - поля по модели `leads`, маска телефона;
  - обязательное согласие со ссылкой на `/privacy`;
  - UTM-метки берутся из URL, сохраняются в `sessionStorage` и передаются с заявкой;
  - скрытое поле honeypot и SmartCaptcha в невидимом режиме.
- **Новые переменные окружения:**
  - backend: `SMARTCAPTCHA_SERVER_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — необязательны в dev и test, обязательны при `APP_ENV=prod`;
  - frontend: `SMARTCAPTCHA_CLIENT_KEY` (читается во время запроса, необязательна).

## Review Focus

1. **Бот заваливает форму:**
   - 4-я заявка с одного IP за час → 429 с `Retry-After`, а первые три сохранены;
   - заполненный honeypot → `201 {"accepted": true}`, но ни строки в БД, ни задачи в очереди;
   - неверный токен капчи → 400 `captcha_failed`, ничего не сохранено.
   
   Тесты в Task 3.
2. **Telegram недоступен или токен неверный.** Заявка сохранена и вернула 201, задача повторяется. После успешной отправки повторная доставка той же задачи второго сообщения не шлёт (`notified_at`). Тесты в Task 4.
3. **Спецсимволы в заявке.** Имя `<b>Анна</b> *_[x](y)` уходит в Telegram как обычный текст, без `parse_mode`, и не ломает отправку. Сообщение длиннее 4096 символов обрезается. Тест в Task 4.
4. **Недопустимый переход через `PATCH`** (`converted → contacted`, `new → converted`, ручной `→ trial_scheduled`, `rejected → rejected`) → 409 `invalid_status_transition`, заявка и история не изменились. Отказ без причины → 422 с полем `reject_reason`. Тесты в Task 5.
5. **Двойная конвертация** (двойной клик или две вкладки) → вторая получает 409 `lead_not_convertible`, семья создана ровно одна. Блокировка — `SELECT … FOR UPDATE` по заявке. Тест в Task 5.

---

## Структура файлов

```
backend/app/
├── main.py                        # + captcha verifier в lifespan, роутеры leads
├── tasks.py                       # setup_worker: + sessionmaker/engine, notifier, регистрация задач notifications
├── core/
│   ├── config.py                  # + smartcaptcha_server_key, telegram_*, валидатор prod
│   ├── phone.py                   # normalize_phone() — вынесено из site_content.schemas
│   └── tasks.py                   # + таймаут enqueue, maxlen, consumer group с начала потока
├── leads/
│   ├── __init__.py
│   ├── models.py                  # Lead, LeadStatusHistory, LeadStatus, ContactMethod
│   ├── status.py                  # TRANSITIONS, MANUAL_TARGETS, can_transition()
│   ├── schemas.py                 # LeadCreate, LeadAccepted, LeadListItem, LeadList, LeadDetail, LeadUpdate, LeadConvert, LeadConverted
│   ├── captcha.py                 # CaptchaVerifier, YandexCaptchaVerifier, DisabledCaptchaVerifier, CaptchaDep
│   ├── service.py                 # create_lead, list_leads, get_lead_detail, update_lead, convert_lead
│   ├── public_router.py           # POST /public/leads
│   └── admin_router.py            # /admin/leads*
└── notifications/
    ├── __init__.py
    ├── notifier.py                # Notifier, TelegramNotifier, DisabledNotifier, NotifyFailed
    └── tasks.py                   # NOTIFY_NEW_LEAD_TASK, format_lead_message(), notify_new_lead, register_tasks
backend/migrations/versions/0004_leads.py
backend/tests/leads/…, backend/tests/notifications/…, backend/tests/core/test_phone.py

frontend/src/
├── components/site/trial-form.tsx (+ test)   # форма заявки; trial-section.tsx переходит на неё
├── lib/phone-mask.ts (+ test)                # formatPhoneInput()
├── lib/utm.ts (+ test)                       # captureUtm(), readUtm()
├── lib/lead-format.ts (+ test)               # LEAD_STATUS_LABELS, CONTACT_METHOD_LABELS, leadContactHref()
└── app/admin/leads/{page,leads-list}.tsx, app/admin/leads/[id]/{page,lead-card,lead-status-actions,lead-convert-dialog,lead-history}.tsx (+ тесты)
```

---

### Task 1: Доработки очереди задач и доступ worker к БД

**Files:**
- Modify: `backend/app/core/tasks.py`, `backend/app/tasks.py`, `backend/app/core/config.py`
- Test: `backend/tests/core/test_tasks.py`, `backend/tests/core/test_config.py`

**Interfaces:**
- Consumes: `create_broker`, `BrokerTaskQueue`, `DelayedRetryMiddleware`, `setup_worker` из плана 3; `create_db_engine`/`create_sessionmaker` из `app.core.db`.
- Produces:
  - **`Settings.task_enqueue_timeout_seconds: float = 2.0`.**
  - **`BrokerTaskQueue.enqueue`** выполняется под `asyncio.timeout(settings.task_enqueue_timeout_seconds)`. Конструктор принимает таймаут: `BrokerTaskQueue(broker, *, timeout_seconds: float)`. Если Redis завис, `enqueue` бросает `TimeoutError` через 2 с; вызывающий код (`request_site_revalidation`, `create_lead`) уже ловит любое исключение.
  - **`create_broker(settings)`:**
    - `RedisStreamBroker(url=..., maxlen=10_000, approximate=True, …)` — имена параметров сверить с установленной taskiq-redis;
    - socket- и connect-таймауты соединений — 5 с: `xread` worker блокируется 2 с, поэтому таймаут должен быть больше;
    - consumer group создаётся с начала потока (`id="0"` / `consumer_id="0"`), чтобы задачи, поставленные до первого старта worker, не терялись.
  - **Комментарий у `default_retry_label=True`:** «каждая задача повторяется при ошибке → задачи обязаны быть идемпотентными».
  - **`setup_worker`** на `WORKER_STARTUP` создаёт `state.engine = create_db_engine(settings)` и `state.sessionmaker = create_sessionmaker(state.engine)`; на `WORKER_SHUTDOWN` — `await state.engine.dispose()`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/core/test_tasks.py — добавить
async def test_enqueue_times_out_when_broker_hangs() -> None:
    class HangingBroker(InMemoryBroker):
        async def kick(self, message):  # type: ignore[override]
            await asyncio.sleep(3600)
    queue = BrokerTaskQueue(HangingBroker(), timeout_seconds=0.05)
    with pytest.raises(TimeoutError):
        await queue.enqueue("test.probe")

def test_broker_caps_stream_length_and_reads_group_from_start(settings: Settings) -> None:
    broker = create_broker(settings)
    assert broker.maxlen == 10_000          # атрибуты — по фактическим именам taskiq-redis
    assert broker.approximate is True
    assert <id/consumer_id группы> == "0"

async def test_worker_state_has_sessionmaker(settings: Settings) -> None:
    broker = setup_worker(InMemoryBroker(), settings)
    await broker.startup()
    try:
        async with broker.state.sessionmaker() as session:
            assert (await session.execute(text("select 1"))).scalar_one() == 1
    finally:
        await broker.shutdown()
```

Если `InMemoryBroker` не вызывает события `WORKER_STARTUP` при `startup()`, вызвать обработчики явно через `broker.event_handlers`. Способ записать в отчёт.

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/core/test_tasks.py --no-cov`
Expected: FAIL — нет `timeout_seconds`, нет `maxlen`, нет `state.sessionmaker`.

- [ ] **Step 3: Реализовать по Interfaces; обновить место создания `BrokerTaskQueue` в `main.py`**

- [ ] **Step 4: Тесты и линтеры**

Run: `just test-backend`, `just lint-backend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "fix(backend): enqueue timeout, capped stream, consumer group from start, DB in worker"
```

---

### Task 2: Модели заявок, таблица переходов, миграция 0004 и общий нормализатор телефона

**Files:**
- Create:
  - `backend/app/core/phone.py`;
  - `backend/app/leads/__init__.py`, `backend/app/leads/models.py`, `backend/app/leads/status.py`;
  - `backend/migrations/versions/0004_leads.py`.
- Modify: `backend/app/site_content/schemas.py` (использовать `normalize_phone`), `backend/migrations/env.py`, `backend/tests/test_migrations.py` (импорт моделей).
- Test: `backend/tests/core/test_phone.py`, `backend/tests/leads/__init__.py`, `backend/tests/leads/test_status.py`, `backend/tests/leads/test_models.py`.

**Interfaces:**
- Produces:
  - **`app.core.phone`:**
    - `PHONE_ERROR` — текст переезжает из `site_content.schemas`, где остаётся реэкспорт или импорт;
    - `normalize_phone(value: str) -> str`. Правила — ровно как в `ContactsBlock` после плана 3: `8XXXXXXXXXX` → `+7…`, `9XXXXXXXXX` → `+79…`, прочие 10 цифр без `+` — ошибка, иначе `^\+?[0-9]{10,15}$` → `+цифры`. При ошибке бросает `ValueError(PHONE_ERROR)`.
    
    `ContactsBlock` вызывает её. Существующие тесты `test_schemas.py` не меняются и остаются зелёными.
  - **Перечисления:**
    - `LeadStatus(StrEnum)`: `NEW="new"`, `CONTACTED="contacted"`, `TRIAL_SCHEDULED="trial_scheduled"`, `CONVERTED="converted"`, `REJECTED="rejected"`;
    - `ContactMethod(StrEnum)`: `TELEGRAM="telegram"`, `WHATSAPP="whatsapp"`, `PHONE="phone"`;
    - в БД — PG enum `lead_status` и `contact_method`.
  - **`Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base)`**, таблица `leads`:
    - `parent_name` String(100), `child_name` String(100), `child_age` Integer;
    - `phone` String(16), `contact_method`, `messenger_handle` String(64) NULL;
    - `goal` Text NULL, `preferred_time` String(200) NULL;
    - `status` (default `new`), `reject_reason` String(500) NULL, `tutor_comment` Text NULL;
    - `family_id` → `families.id` `ondelete="SET NULL"` NULL;
    - `consent_at` timestamptz;
    - `utm_source`, `utm_medium`, `utm_campaign` String(100) NULL;
    - `notified_at` NULL, `anonymized_at` NULL;
    - индексы по `status` и `created_at`.
  - **`LeadStatusHistory(UUIDPrimaryKeyMixin, Base)`**, таблица `lead_status_history`:
    - `lead_id` → `leads.id` `ondelete="CASCADE"`, с индексом;
    - `from_status` NULL, `to_status`;
    - `comment` String(500) NULL;
    - `changed_at` — `server_default=now()`.
  - **`Lead.history`** — `relationship(order_by=LeadStatusHistory.changed_at)`.
  - **`app.leads.status`:**
    - `TRANSITIONS: Mapping[LeadStatus, frozenset[LeadStatus]]` — ровно по таблице из Global Constraints;
    - `MANUAL_TARGETS = frozenset({CONTACTED, REJECTED})`;
    - `can_transition(current: LeadStatus, target: LeadStatus) -> bool`.
  - **Миграция 0004:** оба enum и обе таблицы; `downgrade` удаляет таблицы, затем enum.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/core/test_phone.py
@pytest.mark.parametrize("raw,expected", [
    ("8 (999) 123-45-67", "+79991234567"), ("999 123-45-67", "+79991234567"),
    ("+7 999 123 45 67", "+79991234567"), ("+44 20 7946 0958", "+442079460958")])
def test_normalize_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected

@pytest.mark.parametrize("raw", ["4951234567", "12345", "abc", "+٧٩٩٩١٢٣٤٥٦٧"])
def test_normalize_phone_rejects(raw: str) -> None:
    with pytest.raises(ValueError, match="Укажите телефон"):
        normalize_phone(raw)

# tests/leads/test_status.py
@pytest.mark.parametrize("current,target", [
    ("new", "contacted"), ("new", "trial_scheduled"), ("new", "rejected"),
    ("contacted", "trial_scheduled"), ("contacted", "rejected"),
    ("trial_scheduled", "converted"), ("trial_scheduled", "rejected"), ("trial_scheduled", "contacted"),
    ("rejected", "contacted")])
def test_allowed_transitions(current: str, target: str) -> None:
    assert can_transition(LeadStatus(current), LeadStatus(target))

@pytest.mark.parametrize("current,target", [
    ("new", "converted"), ("new", "new"), ("contacted", "contacted"), ("contacted", "converted"),
    ("rejected", "rejected"), ("rejected", "trial_scheduled"), ("converted", "contacted"),
    ("converted", "rejected")])
def test_forbidden_transitions(current: str, target: str) -> None:
    assert not can_transition(LeadStatus(current), LeadStatus(target))

def test_converted_is_terminal() -> None:
    assert TRANSITIONS[LeadStatus.CONVERTED] == frozenset()

# tests/leads/test_models.py
async def test_history_is_ordered_and_cascades(db_session: AsyncSession) -> None:
    # Lead + две строки истории → lead.history по changed_at; удаление lead удаляет историю
async def test_family_delete_sets_lead_family_null(db_session: AsyncSession) -> None: ...
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/core/test_phone.py tests/leads tests/test_migrations.py --no-cov`
Expected: FAIL — нет модулей.

- [ ] **Step 3: Реализовать по Interfaces** (миграцию писать в стиле 0002/0003; `alembic.ini` — только ASCII)

- [ ] **Step 4: Тесты и линтеры**

Run: `just test-backend`, `just lint-backend`
Expected: зелёное, включая `test_models_match_migrations` и все тесты `site_content`.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): lead models, status transitions, shared phone normalizer"
```

---

### Task 3: `POST /public/leads` — схема, honeypot, SmartCaptcha, rate limit

**Files:**
- Create: `backend/app/leads/schemas.py`, `backend/app/leads/captcha.py`, `backend/app/leads/service.py`, `backend/app/leads/public_router.py`
- Modify: `backend/app/core/config.py`, `backend/app/main.py`, `.env.example`
- Test: `backend/tests/leads/conftest.py`, `backend/tests/leads/test_captcha.py`, `backend/tests/leads/test_public_leads.py`, `backend/tests/core/test_config.py`

**Interfaces:**
- Consumes: `normalize_phone`, `Lead`, `LeadStatusHistory`, `RateLimiter`/`RateLimit`/`RateLimited`, `TaskQueueDep`, `RedisClient`.
- Produces:
  - **Settings:**
    - `smartcaptcha_server_key: SecretStr | None = None`;
    - `telegram_bot_token: SecretStr | None = None`, `telegram_chat_id: str | None = None`;
    - `model_validator`: при `app_env == "prod"` все три обязательны, иначе ошибка «В production обязательны SMARTCAPTCHA_SERVER_KEY, TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID».
  - **`LeadCreate(BaseModel)`** (`extra="forbid"`, `str_strip_whitespace=True`):
    - `parent_name` 1..100, `child_name` 1..100, `child_age: int` 3..18;
    - `phone: str` — через `normalize_phone`, ошибка на поле `phone`;
    - `contact_method: ContactMethod`;
    - `messenger_handle: str | None` ≤ 64 (пустое → `None`);
    - `goal: str | None` ≤ 1000, `preferred_time: str | None` ≤ 200;
    - `consent: Literal[True]` — сообщение «Нужно согласие на обработку персональных данных»;
    - `utm_source`, `utm_medium`, `utm_campaign: str | None` ≤ 100;
    - `captcha_token: str | None` ≤ 5000;
    - `website: str | None = None` ≤ 200 — honeypot.
  - **`LeadAccepted(BaseModel)`:** `accepted: Literal[True] = True`.
  - **Капча (`app.leads.captcha`):**
    - `class CaptchaVerifier(Protocol): async def verify(self, token: str | None, ip: str | None) -> bool`;
    - `DisabledCaptchaVerifier` — всегда `True`;
    - `YandexCaptchaVerifier(client: httpx.AsyncClient, server_key: str)` делает `POST https://smartcaptcha.yandexcloud.net/validate` с form-данными `secret`, `token`, `ip`, таймаут 3 с:
      - HTTP 200 и `{"status": "ok"}` → `True`;
      - HTTP 200 с другим статусом → `False`;
      - пустой токен → `False` без запроса;
      - HTTP не 200 или `httpx.HTTPError` → `True` и warning `captcha_unavailable`;
    - `get_captcha_verifier(request)` берёт `request.app.state.captcha`, который lifespan создаёт по наличию ключа и закрывает его httpx-клиент; `CaptchaDep`.
  - **Ошибка капчи:** `CaptchaFailed(AppError)` — 400, `captcha_failed`, «Не удалось подтвердить, что вы не робот. Обновите страницу и попробуйте ещё раз».
  - **`LEAD_RATE_LIMIT = RateLimit(limit=3, window_seconds=3600)`**, ключ `lead:ip:{ip}`.
  - **`service.create_lead(session: AsyncSession, data: LeadCreate) -> Lead`:** вставляет заявку с `consent_at=now`, статусом `new` и строкой истории `None → new`, затем `flush`.
  - **`public_router`** (`prefix="/public"`, `tags=["public"]`): `@router.post("/leads", status_code=201) async def submit_lead(body: LeadCreate, request: Request, session: DbSession, queue: TaskQueueDep, captcha: CaptchaDep, redis: RedisClient) -> LeadAccepted`. Порядок проверок:
    1. `ip = request.client.host`, если клиент известен;
    2. `count = await limiter.hit(key, LEAD_RATE_LIMIT)`; при `count > 3` → `RateLimited(retry_after)`;
    3. `body.website` не пустой → `LeadAccepted()` без сохранения и без задачи, плюс info-лог `lead_honeypot`;
    4. `await captcha.verify(body.captcha_token, ip)` вернул `False` → `CaptchaFailed`;
    5. `create_lead`, затем `await session.commit()`;
    6. `await service.request_lead_notification(queue, lead.id)` — `enqueue("notifications.notify_new_lead", lead_id=str(lead.id))`; исключения логируются как `lead_notification_enqueue_failed` и не пробрасываются;
    7. ответ `LeadAccepted()`.
    
    Имя задачи — константа `NOTIFY_NEW_LEAD_TASK` в `app/leads/service.py`. Task 4 импортирует её оттуда, чтобы не было цикла `notifications → leads.service`.

- [ ] **Step 1: Написать падающие тесты**

Фикстура в `tests/leads/conftest.py`: `FakeCaptcha(result: bool)` с полем `calls`, подменённая через `dependency_overrides[get_captcha_verifier]`; `valid_lead()` — словарь валидной заявки.

```python
# tests/leads/test_public_leads.py
async def test_submit_saves_lead_with_consent_utm_history_and_enqueues(client, db_session, task_queue) -> None:
    r = await client.post("/api/public/leads", json=valid_lead(utm_source="vk", phone="8 (999) 123-45-67"))
    assert r.status_code == 201 and r.json() == {"accepted": True}
    lead = (await db_session.execute(select(Lead))).scalar_one()
    assert lead.phone == "+79991234567" and lead.utm_source == "vk" and lead.status == "new"
    assert lead.consent_at is not None
    assert [(h.from_status, h.to_status) for h in lead.history] == [(None, "new")]
    assert task_queue.calls == [("notifications.notify_new_lead", {"lead_id": str(lead.id)})]

async def test_fourth_lead_from_same_ip_in_an_hour_is_429(client, db_session) -> None:
    for _ in range(3):
        assert (await client.post("/api/public/leads", json=valid_lead())).status_code == 201
    r = await client.post("/api/public/leads", json=valid_lead())
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["Retry-After"]) > 0
    assert (await db_session.scalar(select(func.count(Lead.id)))) == 3

async def test_honeypot_pretends_success_but_stores_nothing(client, db_session, task_queue) -> None:
    r = await client.post("/api/public/leads", json=valid_lead(website="http://spam.example"))
    assert r.status_code == 201 and r.json() == {"accepted": True}
    assert (await db_session.scalar(select(func.count(Lead.id)))) == 0 and task_queue.calls == []

async def test_failed_captcha_is_400_and_nothing_saved(app, client, db_session) -> None:
    # FakeCaptcha(False) → 400 captcha_failed; count(Lead) == 0

async def test_consent_is_required(client) -> None:
    # consent=False → 422, loc ["body","consent"], message «Нужно согласие на обработку персональных данных»

@pytest.mark.parametrize("field,value", [("child_age", 2), ("child_age", 19), ("phone", "12345"),
    ("contact_method", "email"), ("parent_name", "  "), ("goal", "x" * 1001)])
async def test_invalid_fields_are_422(client, field: str, value: object) -> None: ...

async def test_lead_saved_even_if_enqueue_fails(app, client, db_session) -> None:
    # FakeTaskQueue(fail=True) → 201, count(Lead) == 1, лог lead_notification_enqueue_failed

# tests/leads/test_captcha.py — MockTransport
async def test_yandex_ok_and_failed() -> None:              # {"status":"ok"} → True; {"status":"failed"} → False
async def test_yandex_sends_secret_token_ip() -> None:      # form-данные запроса
async def test_yandex_fails_open_on_error() -> None:        # 500 и ConnectError → True
async def test_empty_token_is_rejected_without_request() -> None: ...

# tests/core/test_config.py — добавить
def test_prod_requires_captcha_and_telegram() -> None: ...  # app_env="prod" без ключей → ValidationError
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/leads tests/core/test_config.py --no-cov`
Expected: FAIL — 404 на `/api/public/leads`, нет `app.leads.captcha`.

- [ ] **Step 3: Реализовать по Interfaces**

Подключить роутер в `create_app`. В `.env.example` добавить три переменные с комментариями: где взять ключи SmartCaptcha (консоль Yandex Cloud) и как получить `chat_id` (написать боту, затем открыть `https://api.telegram.org/bot<token>/getUpdates`).

- [ ] **Step 4: Тесты, линтеры, клиент**

Run: `just test-backend`, `just lint-backend`, `just gen-api`, `just lint-frontend`
Expected: зелёное; в `endpoints/public/public.ts` есть `useSubmitLead`, в `zod/public/public.ts` — `SubmitLeadBody`.

- [ ] **Step 5: Commit**

```bash
git add backend .env.example frontend/openapi.json frontend/src/api/generated
git commit -m "feat(backend): public lead submission with honeypot, SmartCaptcha and rate limit"
```

---

### Task 4: Уведомление репетитора в Telegram

**Files:**
- Create: `backend/app/notifications/__init__.py`, `backend/app/notifications/notifier.py`, `backend/app/notifications/tasks.py`
- Modify: `backend/app/tasks.py` (регистрация и ресурсы)
- Test: `backend/tests/notifications/__init__.py`, `test_notifier.py`, `test_notify_new_lead.py`

**Interfaces:**
- Consumes: `NOTIFY_NEW_LEAD_TASK` из `app.leads.service`; `Lead`; `state.sessionmaker` и `state.http` из Task 1. Склонение «год/года/лет» — локальная функция `_years(n: int) -> str` в `notifications/tasks.py`.
- Produces:
  - **`app.notifications.notifier`:**
    - `class Notifier(Protocol): async def send(self, text: str) -> None`;
    - `class NotifyFailed(Exception)`;
    - `TelegramNotifier(client: httpx.AsyncClient, token: str, chat_id: str)` делает `POST https://api.telegram.org/bot{token}/sendMessage` с JSON `{"chat_id", "text", "disable_web_page_preview": true}`, без `parse_mode`. Ответ не 2xx или `{"ok": false}`, а также `httpx.HTTPError` → `NotifyFailed`; токен в текст исключения не попадает;
    - `DisabledNotifier` — `send` пишет warning `telegram_disabled` и ничего не отправляет.
  - **`app.notifications.tasks`:**
    - `MAX_MESSAGE_LENGTH = 4096`;
    - `format_lead_message(lead: Lead, admin_url: str) -> str` — текст ниже, без пустых строк для отсутствующих полей, обрезка до 4096 с «…» в конце;
    - `async def notify_new_lead(lead_id: str, context: Annotated[Context, TaskiqDepends()]) -> None`:
      - внутри `async with state.sessionmaker() as session` берёт заявку с `SELECT … FOR UPDATE`;
      - нет заявки или `notified_at` уже задан → info-лог и выход;
      - иначе `await state.notifier.send(format_lead_message(lead, f"{public_base_url}/admin/leads/{lead.id}"))`, затем `lead.notified_at = now`, `commit`;
    - `register_tasks(broker)` регистрирует `NOTIFY_NEW_LEAD_TASK`.
  - **`setup_worker`** в `WORKER_STARTUP` кладёт в `state.notifier` `TelegramNotifier`, если заданы токен и chat_id, иначе `DisabledNotifier`; в `state.public_base_url` — `settings.public_base_url`. Задачи `notifications` регистрируются рядом с `site_content`.
  - **Текст сообщения** (обычный текст):
    ```
    Новая заявка на пробное занятие
    Родитель: {parent_name}
    Ребёнок: {child_name}, {child_age} {год|года|лет}
    Связь: {Telegram @handle | WhatsApp | Телефон} · {phone}
    Цель: {goal}
    Удобное время: {preferred_time}
    {admin_url}
    ```
    Если `messenger_handle` пуст, строка Telegram выводится без `@handle`. Строки «Цель» и «Удобное время» есть только при значении.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/notifications/test_notify_new_lead.py
def test_message_contains_name_age_contact_and_link() -> None:
    text = format_lead_message(make_lead(parent_name="Анна", child_name="Маша", child_age=9,
        contact_method="telegram", messenger_handle="anna", phone="+79991234567"), "https://t.example/admin/leads/1")
    assert "Родитель: Анна" in text and "Ребёнок: Маша, 9 лет" in text
    assert "Связь: Telegram @anna · +79991234567" in text and text.endswith("https://t.example/admin/leads/1")
    assert "Цель" not in text

def test_message_is_plain_text_and_truncated() -> None:
    text = format_lead_message(make_lead(parent_name="<b>Анна</b> *_[x](y)", goal="я" * 5000), "u")
    assert "<b>Анна</b> *_[x](y)" in text and len(text) <= 4096 and text.endswith("…")

async def test_task_sends_once_and_marks_notified(worker_state, db_lead) -> None:
    # FakeNotifier с полем sent; два вызова notify_new_lead(str(id)) → одно сообщение, notified_at задан
async def test_task_failure_leaves_lead_unnotified(worker_state, db_lead) -> None:
    # notifier бросает NotifyFailed → исключение пробрасывается (для retry), notified_at остаётся None
async def test_missing_lead_is_noop(worker_state) -> None: ...

# tests/notifications/test_notifier.py — MockTransport
async def test_telegram_posts_plain_text_without_parse_mode() -> None:
    # URL .../bot<token>/sendMessage, JSON без "parse_mode", chat_id и text как переданы
@pytest.mark.parametrize("response", [httpx.Response(500), httpx.Response(429),
    httpx.Response(200, json={"ok": False, "description": "chat not found"})])
async def test_telegram_errors_raise_notify_failed_without_token(response) -> None: ...
async def test_disabled_notifier_logs_and_skips() -> None: ...
```

Фикстура `worker_state`: `TaskiqState` с `sessionmaker`, привязанным к тестовой БД (`db_session` в savepoint-режиме), `notifier=FakeNotifier()` и `public_base_url`. Задачу вызывать напрямую с `Context`-заглушкой.

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/notifications --no-cov`
Expected: FAIL — нет модулей.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Тесты и линтеры**

Run: `just test-backend`, `just lint-backend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): idempotent Telegram notification about new leads"
```

---

### Task 5: Админ-API заявок — список, карточка, статусы, конвертация

**Files:**
- Create: `backend/app/leads/admin_router.py`
- Modify: `backend/app/leads/schemas.py`, `backend/app/leads/service.py`, `backend/app/main.py`
- Test: `backend/tests/leads/test_admin_leads.py`, `backend/tests/leads/test_convert.py`

**Interfaces:**
- Consumes:
  - `can_transition`, `MANUAL_TARGETS`;
  - `families_service.create_family(session, FamilyCreate) -> Family`, `families_service.add_child(session, family_id, ChildCreate) -> ChildDetail`;
  - `auth_service.create_invitation(session, *, family, created_by, prefill_full_name, prefill_phone) -> tuple[str, Invitation]`, `auth_service.build_link(settings, "invite", token)`;
  - `LinkResponse`, `FamilyName`, `ChildCreate`, `TutorUser`.
- Produces:
  - **Схемы:**
    - `LeadHistoryItem`: `from_status: LeadStatus | None`, `to_status`, `comment`, `changed_at`;
    - `LeadListItem`: `id`, `created_at`, `parent_name`, `child_name`, `child_age`, `phone`, `contact_method`, `messenger_handle`, `status`;
    - `LeadList`: `items: list[LeadListItem]`, `total: int`;
    - `LeadDetail`: все поля `Lead`, кроме `anonymized_at`, плюс `history: list[LeadHistoryItem]` и `family_id`;
    - `LeadUpdate`:
      - `status: Literal["contacted", "rejected"] | None`, `comment: str | None` ≤ 500 (комментарий в историю);
      - `reject_reason: str | None` 1..500, `tutor_comment: str | None` ≤ 2000;
      - валидатор: `status == "rejected"` без `reject_reason` → ошибка на поле `reject_reason` «Укажите причину отказа»; `reject_reason` без `status == "rejected"` → ошибка на том же поле;
    - `LeadConvertParent`: `full_name` 1..200, `phone` через `normalize_phone`;
    - `LeadConvert`: `family_name: FamilyName`, `child: ChildCreate`, `parent: LeadConvertParent`;
    - `LeadConverted`: `family_id: UUID`, `invitation: LinkResponse`.
  - **Ошибки:**
    - `InvalidStatusTransition(Conflict)`: `invalid_status_transition`, «Так сменить статус нельзя»;
    - `LeadNotConvertible(Conflict)`: `lead_not_convertible`, «Конвертировать можно после назначения пробного занятия»;
    - `LeadNotFound(NotFound)`: `lead_not_found`, «Заявка не найдена».
  - **Сервис:**
    - `list_leads(session, *, status: LeadStatus | None, q: str | None, limit: int, offset: int) -> LeadList`:
      - сортировка по `created_at desc`;
      - `q` ищется через ILIKE по `parent_name`, `child_name`, `messenger_handle`, а если в `q` не меньше 3 цифр — ещё и по цифрам в `phone`;
      - обезличенные (`anonymized_at` задан) исключены.
    - `get_lead_detail(session, lead_id) -> LeadDetail`.
    - `update_lead(session, lead_id, data: LeadUpdate) -> LeadDetail`:
      - `SELECT … FOR UPDATE`;
      - смена статуса проверяется через `can_transition`, иначе `InvalidStatusTransition`;
      - запись в историю с `comment`;
      - уход из `rejected` очищает `reject_reason`;
      - `tutor_comment` обновляется, если поле передано (`model_fields_set`).
    - `convert_lead(session, lead_id, data: LeadConvert, *, tutor: User, settings: Settings) -> LeadConverted`:
      - `SELECT … FOR UPDATE`;
      - статус не `trial_scheduled` → `LeadNotConvertible`;
      - семья, ребёнок, приглашение с `prefill_full_name=data.parent.full_name` и `prefill_phone=data.parent.phone`;
      - `lead.status = converted`, `lead.family_id = family.id`, история с комментарием «Создана семья {family_name}».
  - **Роутер** (`prefix="/admin"`, `tags=["admin"]`):
    - `GET /admin/leads` → `list_leads` с `status`, `q` (≤ 200), `limit` (1..200, по умолчанию 50), `offset` (≥ 0);
    - `GET /admin/leads/{lead_id}` → `get_lead`;
    - `PATCH /admin/leads/{lead_id}` → `update_lead`;
    - `POST /admin/leads/{lead_id}/convert` (201) → `convert_lead`.

- [ ] **Step 1: Написать падающие тесты**

Фабрика `make_lead(session, **overrides)` — в `tests/leads/conftest.py`. Фикстуры `tutor_client`/`parent_client` — по образцу `tests/site_content/conftest.py`.

```python
# tests/leads/test_admin_leads.py
async def test_list_filters_by_status_and_searches(tutor_client, db_session) -> None:
    # 3 заявки (одна rejected, одна с телефоном +79990001122)
    # ?status=rejected → 1; ?q=маш → по child_name; ?q=0001122 → по телефону; total корректен; порядок created_at desc

async def test_list_paginates(tutor_client, db_session) -> None: ...   # limit=2&offset=2

async def test_detail_includes_history(tutor_client, db_session) -> None: ...

async def test_patch_contacted_writes_history(tutor_client, db_session) -> None:
    lead = await make_lead(db_session)
    r = await tutor_client.patch(f"/api/admin/leads/{lead.id}", json={"status": "contacted", "comment": "Позвонила"})
    assert r.status_code == 200 and r.json()["status"] == "contacted"
    assert r.json()["history"][-1] | {"changed_at": None} == {
        "from_status": "new", "to_status": "contacted", "comment": "Позвонила", "changed_at": None}

@pytest.mark.parametrize("current,target", [("converted", "contacted"), ("rejected", "rejected"),
                                            ("contacted", "contacted")])
async def test_forbidden_patch_is_409_and_changes_nothing(tutor_client, db_session, current, target) -> None:
    # → 409 invalid_status_transition; статус и длина history прежние

async def test_manual_trial_scheduled_or_converted_is_rejected_by_schema(tutor_client, db_session) -> None:
    # {"status": "trial_scheduled"} и {"status": "converted"} → 422

async def test_reject_requires_reason_and_leaving_rejected_clears_it(tutor_client, db_session) -> None:
    # {"status":"rejected"} → 422, loc ["body","reject_reason"]; с причиной → 200, reject_reason задан;
    # затем {"status":"contacted"} → reject_reason is None

async def test_tutor_comment_can_be_set_and_cleared(tutor_client, db_session) -> None: ...

@pytest.mark.parametrize("method,path", [("GET", "/api/admin/leads"), ("GET", "/api/admin/leads/{id}"),
    ("PATCH", "/api/admin/leads/{id}"), ("POST", "/api/admin/leads/{id}/convert")])
async def test_leads_admin_only(client, parent_client, method, path) -> None:
    # аноним → 401, родитель → 404

# tests/leads/test_convert.py
async def test_convert_creates_family_child_invitation_in_one_go(tutor_client, db_session) -> None:
    lead = await make_lead(db_session, status="trial_scheduled", child_name="Маша", child_age=9)
    r = await tutor_client.post(f"/api/admin/leads/{lead.id}/convert", json={
        "family_name": "Семья Маши", "child": {"full_name": "Маша"},
        "parent": {"full_name": "Анна Смирнова", "phone": "8 999 123 45 67"}})
    assert r.status_code == 201
    body = r.json()
    assert "/invite/" in body["invitation"]["url"]
    # в БД: Family name, Child в семье, Invitation.prefill_full_name == "Анна Смирнова",
    # prefill_phone == "+79991234567"; lead.status == converted, lead.family_id == body["family_id"],
    # history[-1] == trial_scheduled → converted с комментарием «Создана семья Семья Маши»

async def test_convert_requires_trial_scheduled(tutor_client, db_session) -> None:
    # status new → 409 lead_not_convertible, семей не прибавилось

async def test_second_convert_is_409_and_one_family_exists(tutor_client, db_session) -> None:
    # два POST подряд → 201, затем 409; count(Family) прибавился на 1
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/leads --no-cov`
Expected: FAIL — 404 на `/api/admin/leads`.

- [ ] **Step 3: Реализовать по Interfaces, подключить роутер**

- [ ] **Step 4: Тесты, линтеры, клиент**

Run: `just test-backend`, `just lint-backend`, `just gen-api`, `just lint-frontend`
Expected: зелёное; хуки `useListLeads`, `useGetLead`, `useUpdateLead`, `useConvertLead`.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(backend): admin leads API with status rules and conversion to a family"
```

---

### Task 6: Frontend — форма заявки на лендинге

**Files:**
- Create:
  - `frontend/src/components/site/trial-form.tsx`;
  - `frontend/src/lib/phone-mask.ts`, `frontend/src/lib/utm.ts`.
- Modify:
  - `frontend/src/components/site/trial-section.tsx` — вместо контактов форма; контакты остаются строкой «или напишите напрямую»;
  - `frontend/src/components/site/landing.tsx` — передаёт `captchaKey`;
  - `frontend/src/app/page.tsx` — читает `SMARTCAPTCHA_CLIENT_KEY` после `connection()`;
  - `frontend/package.json`;
  - `frontend/.env.development` — `SMARTCAPTCHA_CLIENT_KEY=` пустой с комментарием.
- Test: `frontend/src/components/site/trial-form.test.tsx`, `frontend/src/lib/phone-mask.test.ts`, `frontend/src/lib/utm.test.ts`.

**Interfaces:**
- Consumes: `useSubmitLead`, `SubmitLeadBody` (zod), `applyApiErrors`, `errorMessage`, `ApiError`.
- Produces:
  - **`formatPhoneInput(raw: string): string`** — маска российского номера при вводе:
    - `"89991234567"` → `"+7 (999) 123-45-67"`, `"9991"` → `"+7 (999) 1"`;
    - ввод, начинающийся с `+` и не с `+7`, остаётся как есть, только с цифрами, пробелами и `+`;
    - не больше 18 символов для `+7`.
    
    На сервер уходит отформатированная строка, нормализует её backend.
  - **UTM:**
    - `captureUtm(search: string): void` — сохраняет `utm_source`, `utm_medium`, `utm_campaign` (каждое ≤ 100) в `sessionStorage["utm"]`, только если в URL есть хотя бы одна метка;
    - `readUtm(): { utm_source?: string; utm_medium?: string; utm_campaign?: string }`;
    - оба оборачивают `sessionStorage` в `try/catch`.
  - **`TrialForm({ captchaKey }: { captchaKey: string | null })`:**
    - поля: «Ваше имя», «Имя ребёнка», «Возраст ребёнка» (number 3–18), «Телефон» (маска), «Как удобнее связаться» (радио Telegram / WhatsApp / Телефон), «Ник в Telegram» (только для Telegram, необязательно), «Цель занятий», «Удобное время» (необязательные);
    - чекбокс «Согласен(на) на обработку персональных данных» со ссылкой «политикой» → `/privacy`;
    - кнопка «Записаться на пробное»;
    - honeypot `website` — `<input>` в визуально скрытом блоке (`aria-hidden`, `tabIndex={-1}`, `autoComplete="off"`, не `display:none`);
    - `useEffect` вызывает `captureUtm(location.search)`.
  - **Отправка:**
    1. zod-валидация;
    2. если `captchaKey` есть — `InvisibleSmartCaptcha` из `@yandex/smart-captcha` с `visible=true`, токен из `onSuccess` уходит в `captcha_token`; если ключа нет — отправка без капчи;
    3. `POST` с `readUtm()`.
  - **Успех:** вместо формы текст «Спасибо! Заявка отправлена — я свяжусь с вами в ближайшее время.»
  - **Ошибки:**
    - 422 — по полям через `applyApiErrors`;
    - 429 — «Слишком много заявок с этого устройства. Попробуйте позже или напишите напрямую.»;
    - 400 `captcha_failed` и прочие — `Alert` с `errorMessage`.
    
    Введённые данные при ошибке сохраняются.
  - **`page.tsx`:** `LandingContent` после `connection()` читает `process.env.SMARTCAPTCHA_CLIENT_KEY || null` и передаёт `<Landing site={…} captchaKey={…} />`. `Landing` пробрасывает ключ в `TrialSection`.

- [ ] **Step 1: Установить зависимость**

Run: `pnpm --dir frontend add @yandex/smart-captcha`
Expected: зависимость в `package.json`. В отчёте указать проверенный API `InvisibleSmartCaptcha` (props `sitekey`, `visible`, `onSuccess`, `onChallengeHidden`).

- [ ] **Step 2: Написать падающие тесты**

```ts
// src/lib/phone-mask.test.ts
test.each([["89991234567", "+7 (999) 123-45-67"], ["9991234567", "+7 (999) 123-45-67"],
  ["+7999", "+7 (999"], ["9991", "+7 (999) 1"], ["", ""], ["+44 20 7946", "+44 20 7946"]])(
  "formatPhoneInput(%s)", (raw, out) => expect(formatPhoneInput(raw)).toBe(out));

// src/lib/utm.test.ts
test("captures utm from url and reads it back", () => {
  captureUtm("?utm_source=vk&utm_campaign=autumn&x=1");
  expect(readUtm()).toEqual({ utm_source: "vk", utm_campaign: "autumn" });
});
test("url without utm keeps earlier values", () => { /* captureUtm("?a=1") не стирает прежние */ });
test("storage errors are swallowed", () => { /* sessionStorage.setItem бросает → без исключения */ });

// src/components/site/trial-form.test.tsx  (мок fetch, captchaKey=null; отдельный тест — мок @yandex/smart-captcha)
test("requires consent and shows field errors before sending", async () => { /* fetch не вызван */ });
test("phone input is masked as you type", async () => { /* ввод 89991234567 → value "+7 (999) 123-45-67" */ });
test("telegram handle field appears only for Telegram", async () => { ... });
test("submits lead with utm and shows thank-you", async () => {
  // sessionStorage utm → тело POST /api/public/leads содержит utm_source, consent: true, website отсутствует или "";
  // ответ 201 → текст «Спасибо! Заявка отправлена»
});
test("429 shows friendly message and keeps values", async () => { ... });
test("422 lands on the phone field", async () => { /* loc ["body","phone"] → текст под полем «Телефон» */ });
test("with captcha key the token is sent", async () => {
  // мок InvisibleSmartCaptcha вызывает onSuccess("tok") при visible → тело содержит captcha_token: "tok"
});
test("consent label links to /privacy", () => { ... });
```

- [ ] **Step 3: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend test -- src/components/site/trial-form.test.tsx src/lib/phone-mask.test.ts src/lib/utm.test.ts`
Expected: FAIL — модули не найдены.

- [ ] **Step 4: Реализовать по Interfaces; обновить `landing.test.tsx` под новую секцию `#trial`**

- [ ] **Step 5: Проверить**

Run: `just test-frontend`, `just lint-frontend`, `pnpm --dir frontend build` (backend можно не запускать)
Expected: зелёное, сборка проходит.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): trial lesson request form with phone mask, UTM, honeypot and SmartCaptcha"
```

---

### Task 7: Frontend — список заявок `/admin/leads`

**Files:**
- Create: `frontend/src/app/admin/leads/page.tsx`, `frontend/src/app/admin/leads/leads-list.tsx`, `frontend/src/lib/lead-format.ts`
- Modify: `frontend/src/app/admin/admin-shell.tsx` (пункт «Заявки» → `/admin/leads`, перед «Семьи»)
- Test: `frontend/src/app/admin/leads/leads-list.test.tsx`, `frontend/src/lib/lead-format.test.ts`

**Interfaces:**
- Consumes: `useListLeads` и тип `LeadList` из сгенерированного клиента, `formatMoscow`, `errorMessage`, UI-кит (`table`, `badge`, `input`, `select`).
- Produces:
  - **`lead-format.ts`:**
    - `LEAD_STATUS_LABELS: Record<LeadStatus, string>` = `{ new: "Новая", contacted: "Связались", trial_scheduled: "Пробное назначено", converted: "Стала учеником", rejected: "Отказ" }`;
    - `CONTACT_METHOD_LABELS = { telegram: "Telegram", whatsapp: "WhatsApp", phone: "Телефон" }`;
    - `leadContactHref(lead): string` — telegram с ником → `https://t.me/{handle без @}`, whatsapp → `https://wa.me/{цифры}`, иначе `tel:{phone}`.
  - **`page.tsx`** — по образцу `admin/families/page.tsx` (`export const instant = false`, `Suspense`).
  - **`LeadsList`:**
    - параметры URL `?status=&q=&page=` (страница 50 записей, `offset = (page-1)*50`);
    - фильтр-селект «Все / Новая / …»;
    - поиск с debounce 300 мс, который обновляет URL через `router.replace`;
    - таблица: дата (`formatMoscow`), родитель, «ребёнок, возраст», контакт (ссылка `leadContactHref`, текст — способ и телефон), статус (`Badge`);
    - строка — ссылка на `/admin/leads/{id}`;
    - кнопки «Назад» и «Дальше» по `total`;
    - пустое состояние «Заявок пока нет», а при фильтре — «Ничего не найдено».

- [ ] **Step 1: Написать падающие тесты**

```tsx
// src/lib/lead-format.test.ts
test("contact href per method", () => { /* telegram+handle "@anna" → https://t.me/anna; whatsapp → https://wa.me/79991234567; phone → tel:+79991234567; telegram без ника → tel: */ });
// leads-list.test.tsx (мок next/navigation и fetch по образцу families-list.test.tsx)
test("renders leads with status labels and links", async () => { ... });
test("status filter and search go to the URL and the API", async () => {
  // выбор «Отказ» → router.replace с ?status=rejected; запрос /api/admin/leads?status=rejected&limit=50&offset=0
});
test("pagination uses offset", async () => { /* total 120, page=2 → offset=50; «Дальше» активна */ });
test("empty states", async () => { ... });
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend test -- src/app/admin/leads src/lib/lead-format.test.ts`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-frontend`, `just lint-frontend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): admin leads list with status filter, search and paging"
```

---

### Task 8: Frontend — карточка заявки `/admin/leads/[id]`

**Files:**
- Create: `frontend/src/app/admin/leads/[id]/page.tsx`, `lead-card.tsx`, `lead-status-actions.tsx`, `lead-history.tsx`, `lead-convert-dialog.tsx`
- Test: `frontend/src/app/admin/leads/[id]/lead-card.test.tsx`, `lead-status-actions.test.tsx`, `lead-convert-dialog.test.tsx`

**Interfaces:**
- Consumes:
  - хуки `useGetLead`, `getGetLeadQueryKey`, `useUpdateLead`, `useConvertLead`;
  - zod `UpdateLeadBody`, `ConvertLeadBody`;
  - `CopyLinkCard`, `ConfirmDialog` / `Dialog`, `applyApiErrors`, `LEAD_STATUS_LABELS`, `leadContactHref`, `formatMoscow`.
- Produces:
  - **`page.tsx`** — `useParams` внутри `Suspense`, `instant = false`, как `admin/families/[id]/page.tsx`.
  - **`LeadCard`** показывает:
    - все поля заявки: контакт ссылкой, цель, удобное время, UTM, если есть, дату создания;
    - статус (`Badge`) и `reject_reason`, если он задан;
    - редактор `tutor_comment`: textarea и «Сохранить комментарий» → `PATCH {tutor_comment}`;
    - `LeadStatusActions`, `LeadHistory`;
    - для `converted` — ссылку «Открыть семью» → `/admin/families/{family_id}`.
  - **`LeadStatusActions({ lead })`:**
    - кнопки только для разрешённых ручных переходов: «Связались» (→ `contacted`) и «Отказ» (→ `rejected`). Видимость — по той же таблице, что на backend: локальная копия `MANUAL_TRANSITIONS` с тестом, который сверяет её с таблицей спеки;
    - «Связались» открывает диалог с необязательным комментарием;
    - «Отказ» открывает диалог с обязательной причиной (zod из `UpdateLeadBody`);
    - после успеха — `invalidateQueries(getGetLeadQueryKey(id))` и toast «Статус обновлён»;
    - 409 → `Alert` с текстом ошибки.
  - **`LeadConvertDialog({ lead })`:**
    - кнопка «Конвертировать в ученика» активна только при `trial_scheduled`, иначе неактивна с подсказкой «Доступно после назначения пробного занятия»;
    - форма предзаполнена: «Семья» = `Семья {child_name}`, ребёнок = `child_name`, родитель = `parent_name` и `phone`;
    - после успеха вместо формы — `CopyLinkCard` со ссылкой-приглашением и ссылка «Открыть семью»;
    - ошибки 409/422 показываются.
  - **`LeadHistory`** — список «дата · из → в · комментарий» с `LEAD_STATUS_LABELS`; первая строка — «Заявка получена».

- [ ] **Step 1: Написать падающие тесты**

```tsx
// lead-status-actions.test.tsx
test.each([["new", ["Связались", "Отказ"]], ["contacted", ["Отказ"]], ["trial_scheduled", ["Связались", "Отказ"]],
  ["rejected", ["Связались"]], ["converted", []]])("status %s shows %j", (status, buttons) => { ... });
test("reject needs a reason and sends it", async () => {
  // «Отказ» → «Подтвердить» без причины → ошибка, fetch не вызван; ввод «Дорого» → PATCH {status:"rejected", reject_reason:"Дорого"}
});
test("409 is shown", async () => { ... });
test("manual transitions match the spec table", () => { /* MANUAL_TRANSITIONS === ожидаемая карта */ });

// lead-convert-dialog.test.tsx
test("disabled until trial is scheduled", () => { /* status new → кнопка disabled, подсказка видна */ });
test("prefilled from lead and shows invitation link", async () => {
  // POST /api/admin/leads/{id}/convert с family_name «Семья Маши», child.full_name «Маша», parent из заявки
  // ответ → CopyLinkCard с url, ссылка /admin/families/{family_id}
});

// lead-card.test.tsx
test("shows fields, contact link and history", async () => { ... });
test("saves tutor comment", async () => { /* PATCH {tutor_comment: "…"} */ });
test("converted lead links to its family", async () => { ... });
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend test -- "src/app/admin/leads/\[id\]"`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-frontend`, `just lint-frontend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): lead card with status actions, history and conversion"
```

---

### Task 9: Сквозная проверка и документация

**Files:**
- Modify: `README.md` (раздел «Заявки и уведомления»), `.env.example`, `frontend/README.md` (переменная `SMARTCAPTCHA_CLIENT_KEY`)

**Interfaces:**
- Produces:
  - **README:**
    - путь заявки: «форма → `POST /api/public/leads` → задача → Telegram»;
    - как создать бота (BotFather), узнать `TELEGRAM_CHAT_ID` и где взять ключи SmartCaptcha;
    - что без ключей в dev капча и Telegram выключены (в логе `telegram_disabled`);
    - что `trial_scheduled` и «Назначить пробное» появятся в плане 5.

- [ ] **Step 1: Полный прогон**

Run: `just lint`, `just test`
Expected: всё зелёное, покрытие backend ≥ 85%.

- [ ] **Step 2: Сборка без API**

Run: `just down`, затем `pnpm --dir frontend build`
Expected: сборка успешна.

- [ ] **Step 3: Ручная проверка во встроенном браузере** (выполняет контроллер; `just dev`, `just web`)

Expected:
1. На `/` на ширине 375 px форма заполняется: маска телефона работает, без согласия не отправляется. После отправки — «Спасибо!»; UTM из `/?utm_source=test` попали в заявку.
2. В логах worker `notify_new_lead` → `telegram_disabled` (без токена) или сообщение в Telegram (с токеном): `task_finished is_err=False`, тот же `request_id`, что у `POST /api/public/leads`.
3. 4-я заявка за час с того же IP → сообщение про лимит.
4. `/admin/leads`: заявка в списке, фильтр и поиск работают. В карточке «Связались» с комментарием попадает в историю, «Отказ» без причины не проходит.
5. Выставить заявке `trial_scheduled` через SQL (`just` + `psql` или `docker compose exec postgres psql`). «Конвертировать» → ссылка-приглашение, «Открыть семью» показывает семью и ребёнка. Приглашение открывается на `/invite/…` с предзаполненными ФИО и телефоном.

- [ ] **Step 4: Commit**

```bash
git add README.md .env.example frontend/README.md
git commit -m "docs: leads, Telegram notifications and SmartCaptcha setup"
```
