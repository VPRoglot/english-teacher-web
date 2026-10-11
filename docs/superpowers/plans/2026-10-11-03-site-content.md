# План 3 из 7: `site_content` + лендинг — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Публичная страница репетитора (лендинг с SSR, SEO и `/privacy`), контент которой репетитор правит в админке. Блоки хранятся в PostgreSQL, фото — в S3 (локально MinIO). После сохранения worker на Taskiq вызывает revalidate у Next, и страница обновляется за секунды.

**Architecture:**
- **Backend.** Новый модуль `app/site_content`:
  - модели `site_blocks` и `media`;
  - Pydantic-схема на каждый блок;
  - обработка изображений на Pillow;
  - интерфейс `MediaStorage` с реализацией на S3;
  - админ- и публичный роутеры;
  - задача revalidate.
- **Фоновые задачи.** Инфраструктура Taskiq появляется здесь, потому что revalidate — первая фоновая задача:
  - `app/core/tasks.py` — брокер на Redis Streams, retry и request id в метках задачи;
  - API ставит задачи через интерфейс `TaskQueue`;
  - отдельный контейнер `worker`.
- **Frontend.**
  - Лендинг и `/privacy` — серверные компоненты. Данные берутся из `getSite()` с `'use cache'` и тегом `site-content`.
  - Рендер отложен до запроса через `await connection()`, поэтому `next build` не требует запущенного API.
  - Route handler `POST /api/revalidate` с секретом сбрасывает тег.
  - Админка `/admin/site` — клиентские формы на сгенерированных orval-хуках и zod-схемах.

**Tech Stack:**
- Backend: как в планах 1–2, плюс taskiq, taskiq-redis, httpx (переносится в основные зависимости), pillow, aiobotocore (+ types-aiobotocore[s3]), python-multipart, testcontainers[minio].
- Frontend: плюс react-markdown.
- Инфраструктура: MinIO в dev-compose.

**Spec:** `docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md` — используются разделы:
- 2.2 (SSR и revalidate), 2.3, 2.4 (`site_content`);
- 3.4;
- 4.1 (`GET /public/site`), 4.4 (`/admin/site-blocks*`, `/admin/media`), 4.5 п.6;
- 5.1 (`/`, `/privacy`, `/admin/site`), 5.2 (SEO, мобильная версия);
- 6.3 (файлы), 6.4 (`/privacy`), 6.5 (фоновые задачи, request id);
- 7.1–7.2, 8.1 (MinIO в dev), 9 п.3.

**Предыдущие планы:** `2026-10-11-01-foundation.md`, `2026-10-11-02-auth-families.md` (выполнены; код в `main`).

**Уточнения спеки, принятые в этом плане:**
1. **В `hero` добавлено поле `name`** (имя репетитора). Без него не из чего собрать JSON-LD `Person`, заголовок страницы и имя оператора персональных данных на `/privacy`. Спека называет набор полей «начальным».
2. **Отдельного `GET /admin/site-blocks/{key}` нет.** `GET /admin/site-blocks` отдаёт все блоки сразу: редактору нужны все. `PUT /admin/site-blocks/{key}` реализован шестью типизированными маршрутами (`/admin/site-blocks/hero`, …). Пути совпадают со спекой, а orval получает точный тип тела для каждого блока.
3. **Форма заявки в секции `#trial` появится в плане 4.** До этого секция предлагает связаться через контакты из блока `contacts`.

## Global Constraints

- **Всё из планов 1–2 действует:**
  - Python 3.12, префикс `/api`, UUIDv7, `timestamptz`;
  - единый формат ошибок, русские тексты;
  - ruff, mypy strict, eslint, tsc; покрытие ≥ 85%;
  - сессия БД только через `DbSession`;
  - `just gen-api` и коммит `frontend/openapi.json` + `frontend/src/api/generated/**` после каждого изменения API;
  - роутеры импортируют сервисы модулем, имена обработчиков задают operationId;
  - `/admin/*` для не-репетитора → 404, без сессии → 401;
  - коммиты с `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Ключи блоков** — ровно `hero`, `about`, `services`, `reviews`, `faq`, `contacts`. Состав полей и ограничения задаёт таблица в Task 2.
- **Загрузка файлов** (спека 6.3):
  - тип определяется по содержимому (Pillow), не по расширению; разрешены только JPEG, PNG и WebP;
  - размер ≤ 5 МБ (`5 * 1024 * 1024` байт);
  - EXIF удаляется, ориентация из EXIF применяется к пикселям;
  - длинная сторона уменьшается до 2000 px;
  - ключ в S3 — `site/{uuid7}.{jpg|png|webp}`;
  - публичный URL — `{MEDIA_PUBLIC_BASE_URL}/{s3_key}`, по умолчанию `/media/...`.
- **Revalidate** (спека 2.2):
  - тег кеша Next — `site-content`;
  - Next принимает `POST /api/revalidate` с заголовком `Authorization: Bearer ${REVALIDATE_SECRET}`;
  - задача worker `site_content.revalidate_site`: до 5 попыток, пауза растёт экспоненциально, не больше 60 с.
- **Порядок «сохранение → задача».** API ставит задачу только после `commit`. Если поставить задачу не удалось, блок всё равно сохранён (ответ 200), а в лог пишется `site_revalidation_enqueue_failed`.
- **Markdown** отрисовывается через react-markdown без сырого HTML. Ссылки `javascript:` не выводятся.
- **Индексация.** robots.txt закрывает `/admin`, `/cabinet`, `/invite`, `/reset`, `/login`, `/api`. У этих зон, кроме `/api`, есть ещё `robots: noindex` в metadata.
- **Сборка.** `pnpm build` проходит без запущенного API. Лендинг, `/privacy`, `robots.txt` и `sitemap.xml` читают данные и env только во время запроса (после `await connection()`).
- **Переменные окружения (новые):**
  - backend: `REVALIDATE_URL`, `REVALIDATE_SECRET` (≥ 16 символов, обязательна), `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_ADDRESSING_STYLE`, `MEDIA_PUBLIC_BASE_URL`;
  - frontend: `API_INTERNAL_URL`, `SITE_URL`, `REVALIDATE_SECRET`, `MEDIA_PROXY_URL` (только dev).

## Review Focus

1. **Подложный или опасный файл вместо фото:**
   - текст, HTML или SVG с расширением `.jpg`, GIF, обрезанный JPEG → 415 `unsupported_media_type`;
   - «декомпрессионная бомба» (больше 40 Мп при малом размере файла) → 413 `file_too_large`;
   - в обоих случаях в S3 и в `media` ничего не появляется.
   
   Тесты в Task 3.
2. **Фото с телефона.** JPEG с GPS в EXIF и `Orientation=6` → в сохранённом файле EXIF нет, а портретное фото остаётся портретным (ширина и высота переставлены). Тест в Task 3.
3. **XSS через контент:**
   - `<script>` или `<img onerror>` в тексте «О себе» и ссылка `[x](javascript:alert(1))` → на странице нет ни `<script>`, ни `href="javascript:…"`;
   - `</script>` в `hero.name` не разрывает JSON-LD.
   
   Тесты в Task 6 и Task 7.
4. **Устаревший лендинг:**
   - задача revalidate выполнилась раньше `commit` — старый контент закеширован бы надолго;
   - Redis недоступен при сохранении → блок всё равно сохраняется.
   
   Тесты порядка «commit → задача» и сбоя постановки — в Task 4. Повтор при ответе Next 5xx — в Task 1.
5. **Несуществующее фото в блоке** (опечатка в id, чужой UUID) → 422 с полем `details.fields[].loc`, блок не сохраняется. Если строка `media` всё же исчезла, публичная страница показывает блок без фото, а не битую картинку. Тесты в Task 4.

---

## Структура файлов

```
backend/app/
├── main.py                          # + брокер и очередь задач, хранилище медиа, роутеры site_content
├── worker.py                        # точка входа worker: broker = setup_worker(create_broker(...))
├── tasks.py                         # setup_worker(): регистрация задач, ресурсы worker (httpx)
├── core/
│   ├── config.py                    # + revalidate_*, s3_*, media_public_base_url
│   └── tasks.py                     # create_broker, TaskQueue, BrokerTaskQueue, RequestIdTaskMiddleware
└── site_content/
    ├── __init__.py
    ├── models.py                    # SiteBlock, Media
    ├── schemas.py                   # схемы блоков, BLOCK_SCHEMAS, публичные/админ-ответы, MediaOut
    ├── errors.py                    # UnsupportedImage, FileTooLarge, StorageUnavailable
    ├── images.py                    # process_image()
    ├── storage.py                   # MediaStorage, S3MediaStorage, MediaStorageDep
    ├── service.py                   # upload_media, get_site_blocks, save_block, get_public_site, request_site_revalidation
    ├── tasks.py                     # REVALIDATE_SITE_TASK, HttpRevalidator, revalidate_site, register_tasks
    ├── admin_router.py              # /admin/site-blocks*, /admin/media
    └── public_router.py             # /public/site
backend/migrations/versions/0003_site_content.py   # таблицы + заглушки блоков
backend/tests/
├── conftest.py                      # + MinIO, FakeTaskQueue, новые настройки
├── core/test_tasks.py
└── site_content/{conftest,test_schemas,test_models,test_images,test_media_api,
                  test_revalidate_task,test_admin_blocks,test_public_site}.py

frontend/src/
├── app/
│   ├── page.tsx                     # лендинг (Suspense + connection + getSite) + generateMetadata + JSON-LD
│   ├── error.tsx                    # понятная ошибка вместо «Application error»
│   ├── privacy/page.tsx
│   ├── robots.ts, sitemap.ts
│   ├── api/revalidate/route.ts
│   └── admin/site/{page,site-editor,hero-editor,about-editor,contacts-editor,
│                   services-editor,reviews-editor,faq-editor,photo-field}.tsx (+ тесты)
├── components/site/                 # landing, site-header, site-footer, *-section, markdown, contact-links, privacy-policy
├── lib/
│   ├── server-env.ts                # serverEnv()
│   ├── site-content.ts              # SITE_CONTENT_TAG, getSite()
│   ├── seo.ts                       # buildMetadata, buildJsonLd, jsonLdScript
│   └── site-format.ts               # formatRub, pluralRu, contactLinks
└── test/site-fixture.ts             # siteFixture: PublicSite для тестов
infra/docker-compose.yml             # + worker, env для web
infra/docker-compose.dev.yml         # + minio, minio-init, worker (dev)
```

---

### Task 1: Taskiq — брокер, очередь задач, worker и задача revalidate

**Files:**
- Modify:
  - `backend/pyproject.toml`, `backend/uv.lock`;
  - `backend/app/core/config.py`, `backend/app/main.py`;
  - `backend/tests/conftest.py`, `backend/tests/core/test_config.py`;
  - `infra/docker-compose.yml`, `infra/docker-compose.dev.yml`;
  - `justfile`, `.env.example`.
- Create:
  - `backend/app/core/tasks.py`, `backend/app/tasks.py`, `backend/app/worker.py`;
  - `backend/app/site_content/__init__.py`, `backend/app/site_content/tasks.py`.
- Test: `backend/tests/core/test_tasks.py`, `backend/tests/site_content/__init__.py`, `backend/tests/site_content/test_revalidate_task.py`.

**Interfaces:**
- Produces:
  - **Settings:**
    - `revalidate_url: str = "http://localhost:3000/api/revalidate"`;
    - `revalidate_secret: SecretStr` — обязательная, валидатор требует длину ≥ 16 («REVALIDATE_SECRET: не короче 16 символов»).
  - **`app.core.tasks`:**
    - `create_broker(settings: Settings) -> AsyncBroker` — `RedisStreamBroker(url=settings.redis_url)` с middlewares:
      - `SmartRetryMiddleware(default_retry_count=5, default_delay=5, use_jitter=True, use_delay_exponent=True, max_delay_exponent=60)`;
      - `RequestIdTaskMiddleware()`.
    - `class TaskQueue(Protocol): async def enqueue(self, task_name: str, /, **kwargs: Any) -> None`.
    - `class BrokerTaskQueue(TaskQueue)` — `__init__(self, broker: AsyncBroker)`. `enqueue` делает `AsyncKicker(task_name=..., broker=..., labels=...)` и `.kiq(**kwargs)`. В `labels` кладётся `{"request_id": get_request_id()}`, если request id есть. Задача ставится по имени, поэтому API не импортирует модули задач.
    - `class RequestIdTaskMiddleware(TaskiqMiddleware)`:
      - `pre_execute` привязывает к structlog contextvars `request_id` (из меток) и `task_name`, пишет `task_started`;
      - `post_execute` пишет `task_finished` с `is_err` и очищает contextvars.
    - `get_task_queue(request: Request) -> TaskQueue` — возвращает `request.app.state.task_queue`.
    - `TaskQueueDep = Annotated[TaskQueue, Depends(get_task_queue)]`.
  - **Lifespan в `main.py`:** `app.state.broker = create_broker(settings)`, затем `await broker.startup()` и `app.state.task_queue = BrokerTaskQueue(broker)`; в `finally` — `await broker.shutdown()`. Приложение должно стартовать при недоступном Redis (существующие тесты `tests/core/test_ready.py::test_ready_reports_redis_down` остаются зелёными). Если `startup()` клиента подключается к Redis, ленивость нужно обеспечить самому, а не убирать тест.
  - **`app.site_content.tasks`:**
    - `REVALIDATE_SITE_TASK = "site_content.revalidate_site"`;
    - `class RevalidateFailed(Exception)`;
    - `class Revalidator(Protocol): async def revalidate(self) -> None`;
    - `class HttpRevalidator` — `__init__(self, client: httpx.AsyncClient, url: str, secret: str)`; `revalidate` делает `POST url` с `Authorization: Bearer {secret}` и `X-Request-ID` (если есть). Ответ не 2xx или ошибка сети → `RevalidateFailed` (это запускает retry);
    - `async def revalidate_site(context: Annotated[Context, TaskiqDepends()]) -> None` — вызывает `context.state.revalidator.revalidate()`;
    - `register_tasks(broker: AsyncBroker) -> None` — `broker.register_task(revalidate_site, task_name=REVALIDATE_SITE_TASK, retry_on_error=True, max_retries=5)`.
  - **`app.tasks.setup_worker(broker: AsyncBroker, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> AsyncBroker`:**
    - вызывает `register_tasks`;
    - на `TaskiqEvents.WORKER_STARTUP` кладёт в `state.http` `httpx.AsyncClient(timeout=10, transport=transport)`, а в `state.revalidator` — `HttpRevalidator(...)`;
    - на `WORKER_SHUTDOWN` делает `aclose()`.
  - **`app/worker.py`** — три строки: `settings = get_settings()`, `configure_logging(settings.log_level, settings.log_json)`, `broker = setup_worker(create_broker(settings), settings)`. Тесты этот модуль не импортируют.
  - **Тестовые фикстуры (`tests/conftest.py`):**
    - `class FakeTaskQueue` с полями `calls: list[tuple[str, dict[str, Any]]]` и `fail: bool = False`; при `fail` метод `enqueue` бросает `ConnectionError`;
    - фикстура `task_queue`;
    - фикстура `app` подменяет `get_task_queue` через `dependency_overrides`;
    - `settings` получает `revalidate_secret="test-revalidate-secret"`.
  - **Compose, justfile и `.env.example`:**
    - сервис `worker` (`<<: *backend`, `command: ["taskiq", "worker", "app.worker:broker", "--workers", "1"]`, `environment: REVALIDATE_URL: http://web:3000/api/revalidate`, зависит от `migrate` и `redis`, `restart: unless-stopped`);
    - в dev: volume `../backend/app:/app/app`, `REVALIDATE_URL: http://host.docker.internal:3000/api/revalidate`, `extra_hosts: ["host.docker.internal:host-gateway"]`. Hot reload для worker не нужен: после правки задач нужен `just restart worker`;
    - рецепты `restart *args` и `worker` (локальный запуск `uv --directory backend run taskiq worker app.worker:broker`);
    - в `.env.example` — `REVALIDATE_SECRET=dev-revalidate-secret-change-me` с комментарием.

- [ ] **Step 1: Добавить зависимости**

Run: `uv --directory backend remove --dev httpx`, затем `uv --directory backend add taskiq taskiq-redis httpx`
Expected: `uv.lock` обновлён, `just test-backend --no-cov -q` зелёный.

- [ ] **Step 2: Написать падающие тесты**

```python
# tests/core/test_tasks.py
async def test_enqueue_kicks_task_by_name_with_request_id_label() -> None:
    broker = InMemoryBroker()
    seen: dict[str, Any] = {}

    async def probe(x: int, context: Annotated[Context, TaskiqDepends()]) -> None:
        seen["x"] = x
        seen["labels"] = context.message.labels

    broker.register_task(probe, task_name="test.probe")
    await broker.startup()
    token = _request_id.set("rid-1")          # contextvar из app.core.request_id
    try:
        await BrokerTaskQueue(broker).enqueue("test.probe", x=1)
        await broker.wait_all()
    finally:
        _request_id.reset(token)
        await broker.shutdown()
    assert seen == {"x": 1, "labels": {"request_id": "rid-1"}}

def test_broker_retries_five_times(settings: Settings) -> None:
    broker = create_broker(settings)
    retry = [m for m in broker.middlewares if isinstance(m, SmartRetryMiddleware)]
    assert len(retry) == 1 and retry[0].default_retry_count == 5

# tests/site_content/test_revalidate_task.py
async def test_http_revalidator_posts_with_bearer_secret() -> None:
    requests: list[httpx.Request] = []
    transport = httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(204))
    async with httpx.AsyncClient(transport=transport) as client:
        await HttpRevalidator(client, "http://web.test/api/revalidate", "s3cret-s3cret-123").revalidate()
    assert [(r.method, str(r.url)) for r in requests] == [("POST", "http://web.test/api/revalidate")]
    assert requests[0].headers["Authorization"] == "Bearer s3cret-s3cret-123"

@pytest.mark.parametrize("status", [401, 500, 503])
async def test_http_revalidator_raises_on_error_status(status: int) -> None:
    # MockTransport → httpx.Response(status) → pytest.raises(RevalidateFailed)

async def test_http_revalidator_raises_on_network_error() -> None:
    # MockTransport бросает httpx.ConnectError → RevalidateFailed

async def test_worker_runs_revalidate_task(settings: Settings) -> None:
    # broker = setup_worker(InMemoryBroker(), settings, transport=mock); await broker.startup()
    # await BrokerTaskQueue(broker).enqueue(REVALIDATE_SITE_TASK); await broker.wait_all()
    # mock получил ровно один POST на settings.revalidate_url с Bearer test-revalidate-secret

# tests/core/test_config.py — добавить
def test_revalidate_secret_is_required_and_long_enough() -> None:
    # Settings(_env_file=None, database_url=..., redis_url=..., <s3 из Task 3 пока нет>) без secret → ValidationError
    # revalidate_secret="short" → ValidationError с текстом «не короче 16 символов»
```

- [ ] **Step 3: Запустить — убедиться, что падают**

Run: `just test-backend tests/core/test_tasks.py tests/site_content tests/core/test_config.py --no-cov`
Expected: FAIL — `ModuleNotFoundError: app.core.tasks` / `app.site_content.tasks`.

- [ ] **Step 4: Реализовать по Interfaces**

Сигнатуры `SmartRetryMiddleware`, `RedisStreamBroker`, `AsyncKicker` и `InMemoryBroker.wait_all` сверить с установленной версией taskiq. Если без `schedule_source` пауза retry не поддерживается, то передать `RedisScheduleSource` нельзя без scheduler-процесса. В этом случае оставить встроенную задержку middleware и записать решение в отчёт.

- [ ] **Step 5: Запустить тесты и линтеры**

Run: `just test-backend`, `just lint-backend`
Expected: всё зелёное, покрытие ≥ 85%.

- [ ] **Step 6: Проверить worker в Docker**

Run: `cp .env.example .env` (если нет), `just dev`, `just logs worker`
Expected: worker стартовал без ошибок и слушает очередь. Next ещё не запущен — это нормально.

- [ ] **Step 7: Commit**

```bash
git add backend infra justfile .env.example
git commit -m "feat(backend): taskiq worker with retrying revalidate task"
```

---

### Task 2: Модели, схемы блоков и миграция 0003 с заглушками

**Files:**
- Create: `backend/app/site_content/models.py`, `backend/app/site_content/schemas.py`, `backend/migrations/versions/0003_site_content.py`
- Modify: `backend/tests/test_migrations.py` (импорт `app.site_content.models`), `backend/migrations/env.py` (если модели регистрируются там)
- Test: `backend/tests/site_content/test_schemas.py`, `backend/tests/site_content/test_models.py`

**Interfaces:**
- Produces:
  - `SiteBlock(Base)`:
    - `__tablename__ = "site_blocks"`;
    - `key: Mapped[str]` — `String(32)`, первичный ключ;
    - `data: Mapped[dict[str, Any]]` — `JSONB`;
    - `updated_at` — `server_default=now()`, `onupdate=now()`;
    - `CheckConstraint("key IN ('hero','about','services','reviews','faq','contacts')", name="key_known")`.
  - `Media(UUIDPrimaryKeyMixin, Base)`:
    - `__tablename__ = "media"`;
    - `s3_key` — `String(200)`, unique;
    - `content_type` — `String(50)`;
    - `size_bytes`, `width`, `height` — `Integer`;
    - `created_at` — `server_default=now()`.
  - `BlockKey(StrEnum)`: `HERO="hero"`, `ABOUT="about"`, `SERVICES="services"`, `REVIEWS="reviews"`, `FAQ="faq"`, `CONTACTS="contacts"`.
  - Схемы с базовым `model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)`. Поля — по таблице ниже. Длины — в символах; «1..N» значит, что поле обязательно и не пустое после обрезки пробелов.

| Схема | Поля |
|---|---|
| `HeroBlock` | `name` 1..100; `title` 1..120; `subtitle` 1..300; `photo_media_id: UUID \| None = None`; `cta_text` 1..40 |
| `AboutBlock` | `text` 1..5000 (markdown); `photo_media_id: UUID \| None = None`; `credentials: list[str 1..200]`, ≤ 20 элементов |
| `ServiceItem` | `title` 1..120; `description` 0..1000; `duration_min: int` 15..240; `price_rub: int` 0..100000; `format` 1..60 |
| `ServicesBlock` | `items: list[ServiceItem]`, ≤ 20 |
| `ReviewItem` | `author` 1..100; `text` 1..2000; `child_age: int \| None` 3..18; `photo_media_id: UUID \| None = None` |
| `ReviewsBlock` | `items: list[ReviewItem]`, ≤ 30 |
| `FaqItem` | `question` 1..300; `answer` 1..2000 |
| `FaqBlock` | `items: list[FaqItem]`, ≤ 30 |
| `ContactsBlock` | `telegram`, `whatsapp`, `phone`, `email: EmailStr`, `working_hours_text` 1..200 — все `\| None = None` |

  - **Нормализация `ContactsBlock`** — `field_validator(mode="before")`:
    - пустая строка или пробелы → `None`;
    - `telegram`: убираются префиксы `https://t.me/`, `http://t.me/`, `t.me/` и `@`; результат должен соответствовать `^[A-Za-z0-9_]{5,32}$`, иначе ошибка «Укажите имя пользователя Telegram, например @anna_english»;
    - `phone` и `whatsapp`: удаляются пробелы, `-`, `(`, `)`; номер `8XXXXXXXXXX` (11 цифр) превращается в `+7XXXXXXXXXX`; результат должен соответствовать `^\+?\d{10,15}$` и хранится как `+` и цифры, иначе ошибка «Укажите телефон в формате +7 999 123-45-67».
  - `BLOCK_SCHEMAS: Mapping[BlockKey, type[BaseModel]]` — словарь «ключ → схема».
  - `referenced_media_ids(block: BaseModel) -> list[tuple[tuple[str | int, ...], uuid.UUID]]` возвращает пары «путь поля + id фото»:
    - hero и about → `[(("photo_media_id",), id)]`;
    - reviews → `[(("items", i, "photo_media_id"), id), ...]`;
    - поля со значением `None` пропускаются.
  - **Миграция 0003:** таблицы `site_blocks` и `media`, плюс `op.bulk_insert` шести заглушек с замороженным JSON. Миграция не импортирует `app.*`. Заглушки:
    - `hero`: `{"name": "Имя Фамилия", "title": "Английский для детей и подростков", "subtitle": "Индивидуальные онлайн-занятия: разговорная практика, школьная программа, подготовка к ОГЭ и ЕГЭ", "photo_media_id": null, "cta_text": "Записаться на пробное"}`;
    - `about`: `{"text": "Расскажите здесь о себе: опыт, подход к занятиям, чем вы отличаетесь.", "photo_media_id": null, "credentials": []}`;
    - `services`: `{"items": [{"title": "Пробное занятие", "description": "Знакомство, определение уровня и целей", "duration_min": 30, "price_rub": 0, "format": "Онлайн"}]}`;
    - `reviews`: `{"items": []}`;
    - `faq`: `{"items": [{"question": "Как проходит пробное занятие?", "answer": "Знакомимся, определяем уровень и цели, обсуждаем расписание."}]}`;
    - `contacts`: все пять полей `null`.
    
    `downgrade` удаляет обе таблицы.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/site_content/test_schemas.py
def test_hero_strips_whitespace_and_rejects_blank_title() -> None:
    hero = HeroBlock(name="  Анна  ", title="Т", subtitle="С", cta_text="Записаться")
    assert hero.name == "Анна"
    with pytest.raises(ValidationError):
        HeroBlock(name="Анна", title="   ", subtitle="С", cta_text="Записаться")

def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        FaqItem(question="В?", answer="О", extra="x")

@pytest.mark.parametrize("field,value", [("duration_min", 10), ("duration_min", 241),
                                         ("price_rub", -1), ("price_rub", 100_001)])
def test_service_item_limits(field: str, value: int) -> None: ...

def test_services_at_most_20_items() -> None: ...           # 21 элемент → ValidationError

@pytest.mark.parametrize("age,ok", [(2, False), (3, True), (18, True), (19, False), (None, True)])
def test_review_child_age_range(age: int | None, ok: bool) -> None: ...

@pytest.mark.parametrize("raw,expected", [
    ("@anna_english", "anna_english"), ("https://t.me/anna_english", "anna_english"),
    ("t.me/anna_english", "anna_english"), ("", None), ("   ", None)])
def test_contacts_normalizes_telegram(raw: str, expected: str | None) -> None: ...

@pytest.mark.parametrize("raw,expected", [
    ("8 (999) 123-45-67", "+79991234567"), ("+7 999 123 45 67", "+79991234567"),
    ("+44 20 7946 0958", "+442079460958")])
def test_contacts_normalizes_phone_and_whatsapp(raw: str, expected: str) -> None: ...

@pytest.mark.parametrize("field,value", [("telegram", "ann"), ("telegram", "anna english"),
                                         ("phone", "12345"), ("whatsapp", "abc"), ("email", "not-an-email")])
def test_contacts_rejects_invalid(field: str, value: str) -> None: ...

def test_referenced_media_ids_reports_paths() -> None:
    a, b = uuid7(), uuid7()
    reviews = ReviewsBlock(items=[ReviewItem(author="А", text="Т"),
                                  ReviewItem(author="Б", text="Т", photo_media_id=a)])
    assert referenced_media_ids(reviews) == [(("items", 1, "photo_media_id"), a)]
    hero = HeroBlock(name="А", title="Т", subtitle="С", cta_text="К", photo_media_id=b)
    assert referenced_media_ids(hero) == [(("photo_media_id",), b)]

# tests/site_content/test_models.py
async def test_migration_seeds_valid_stub_for_every_block(db_session: AsyncSession) -> None:
    rows = (await db_session.execute(select(SiteBlock))).scalars().all()
    assert {r.key for r in rows} == {k.value for k in BlockKey}
    for row in rows:
        BLOCK_SCHEMAS[BlockKey(row.key)].model_validate(row.data)

async def test_unknown_block_key_is_rejected_by_db(db_session: AsyncSession) -> None:
    # INSERT SiteBlock(key="pricing", data={}) → IntegrityError (ck_site_blocks_key_known)
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/site_content tests/test_migrations.py --no-cov`
Expected: FAIL — нет `app.site_content.models` / `schemas`.

- [ ] **Step 3: Реализовать модели, схемы и миграцию по Interfaces**

Сгенерировать каркас миграции командой `uv --directory backend run alembic revision --autogenerate -m site_content --rev-id 0003`. Это требует dev-БД из `just dev` и localhost-адресов в `backend/.env`. Затем дописать вставку заглушек и проверить, что `alembic.ini` по-прежнему только ASCII.

- [ ] **Step 4: Запустить тесты**

Run: `just test-backend`, `just lint-backend`
Expected: зелёное, включая `test_upgrade_downgrade_upgrade` и `test_models_match_migrations`.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): site blocks and media models, block schemas, seeded stubs"
```

---

### Task 3: Медиа — обработка изображений, S3 и `POST /admin/media`

**Files:**
- Create:
  - `backend/app/site_content/errors.py`, `images.py`, `storage.py`;
  - `backend/app/site_content/service.py`, `admin_router.py`.
- Modify:
  - `backend/app/core/config.py`, `backend/app/main.py`;
  - `backend/pyproject.toml`, `backend/uv.lock`;
  - `backend/tests/conftest.py`;
  - `infra/docker-compose.dev.yml`, `.env.example`.
- Test: `backend/tests/site_content/conftest.py`, `test_images.py`, `test_media_api.py`.

**Interfaces:**
- Consumes: `Media`, `new_uuid7`, `TutorUser`, `DbSession`, `API_ERROR_RESPONSES`.
- Produces:
  - **Settings:**
    - `s3_endpoint_url: str | None = None`, `s3_region: str = "us-east-1"`;
    - `s3_bucket: str`, `s3_access_key: str`, `s3_secret_key: SecretStr` — обязательные;
    - `s3_addressing_style: Literal["path", "virtual"] = "path"`;
    - `media_public_base_url: str = "/media"` — завершающий `/` убирается.
  - **`app.site_content.errors`:**
    - `UnsupportedImage(AppError)`: 415, `unsupported_media_type`, «Поддерживаются только изображения JPEG, PNG и WebP»;
    - `FileTooLarge(AppError)`: 413, `file_too_large`, «Файл слишком большой: до 5 МБ и не больше 40 мегапикселей»;
    - `StorageUnavailable(AppError)`: 503, `storage_unavailable`, «Хранилище файлов недоступно. Попробуйте позже».
  - **`app.site_content.images`:**
    - константы `MAX_UPLOAD_BYTES = 5 * 1024 * 1024`, `MAX_SIDE = 2000`, `MAX_PIXELS = 40_000_000`;
    - `@dataclass(frozen=True) class ProcessedImage` с полями `data: bytes`, `content_type: str`, `extension: str`, `width: int`, `height: int`;
    - `process_image(data: bytes) -> ProcessedImage` — синхронная, работает по шагам:
      1. `Image.open`; формат не из `{"JPEG", "PNG", "WEBP"}` или ошибка разбора → `UnsupportedImage`;
      2. `width * height > MAX_PIXELS` (проверяется до `load()`, а `DecompressionBombWarning`/`Error` перехватываются) → `FileTooLarge`;
      3. `load()`; обрезанный файл → `UnsupportedImage`;
      4. `ImageOps.exif_transpose`, затем `thumbnail((MAX_SIDE, MAX_SIDE))`;
      5. сохранение в исходный формат без EXIF (ICC-профиль сохраняется). JPEG — `quality=85, optimize=True`; режимы, кроме `RGB`/`L`, переводятся в `RGB`. У анимированных файлов берётся первый кадр;
      6. расширения: `jpg`, `png`, `webp`.
  - **`app.site_content.storage`:**
    - `class MediaStorage(Protocol): async def put(self, key: str, data: bytes, content_type: str) -> None`;
    - `class S3MediaStorage(MediaStorage)` — `__init__(self, settings: Settings)`; `put` создаёт клиент aiobotocore на каждый вызов с `AioConfig(s3={"addressing_style": ...}, connect_timeout=5, read_timeout=30, retries={"max_attempts": 2})`; любые `BotoCoreError`/`ClientError` → `StorageUnavailable`;
    - `get_media_storage(request: Request) -> MediaStorage` — возвращает `request.app.state.media_storage`, который создаётся в lifespan;
    - `MediaStorageDep`.
  - **`app.site_content.schemas`:**
    - `MediaOut(BaseModel)`: `id: UUID`, `url: str`, `content_type: str`, `size_bytes: int`, `width: int`, `height: int`;
    - `media_url(settings: Settings, s3_key: str) -> str`.
  - **`app.site_content.service.upload_media(session: AsyncSession, storage: MediaStorage, settings: Settings, data: bytes) -> MediaOut`:**
    - `process_image` в `anyio.to_thread.run_sync`;
    - ключ `site/{new_uuid7()}.{ext}`;
    - сначала `storage.put`, затем вставка `Media` и `flush`. Если упадёт вставка, в бакете останется объект-сирота — это допустимо.
  - **Роутер `app.site_content.admin_router.router`** (`prefix="/admin"`, `tags=["admin"]`, `responses=API_ERROR_RESPONSES`): `@router.post("/media", status_code=201) async def upload_media(file: UploadFile, request: Request, _: TutorUser, session: DbSession, storage: MediaStorageDep) -> MediaOut`. Обработчик читает `await file.read(MAX_UPLOAD_BYTES + 1)`; если прочитано больше лимита → `FileTooLarge`.
  - **Dev-compose:**
    - сервис `minio` (`minio/minio`, `server /data --console-address :9001`, порты 9000 и 9001, volume `miniodata`, `MINIO_ROOT_USER=${S3_ACCESS_KEY}`, `MINIO_ROOT_PASSWORD=${S3_SECRET_KEY}`, healthcheck `mc ready local` или `curl -f http://127.0.0.1:9000/minio/health/live`);
    - одноразовый `minio-init` (`minio/mc`): `mc alias set`, `mc mb --ignore-existing`, `mc anonymous set download` на `${S3_BUCKET}`;
    - `api` и `worker` зависят от `minio-init: service_completed_successfully`.
  - **`.env.example`:** `S3_ENDPOINT_URL=http://minio:9000`, `S3_BUCKET=media`, `S3_ACCESS_KEY=minio-dev`, `S3_SECRET_KEY=minio-dev-secret` и строка для `backend/.env` с `S3_ENDPOINT_URL=http://localhost:9000`.
  - **Тестовые фикстуры:**
    - `minio` — session-фикстура `MinioContainer()` из `testcontainers.community.minio`;
    - `minio_client` — клиент `minio.Minio` из контейнера;
    - бакет `media-test` создаётся один раз;
    - `settings` получает `s3_endpoint_url=f"http://{host}:{port}"`, ключи контейнера и `s3_bucket="media-test"`.

- [ ] **Step 1: Добавить зависимости**

Run: `uv --directory backend add pillow aiobotocore python-multipart` и `uv --directory backend add --dev "types-aiobotocore[s3]" "testcontainers[postgres,redis,minio]"`
Expected: `uv.lock` обновлён.

- [ ] **Step 2: Написать падающие тесты**

Хелперы в `tests/site_content/conftest.py`: `make_image(fmt: str, size: tuple[int, int], *, mode="RGB", exif: Image.Exif | None = None) -> bytes`.

```python
# tests/site_content/test_images.py
def test_jpeg_exif_is_stripped_and_orientation_applied() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6                                     # Orientation: повернуть на 90°
    exif[0x8825] = {2: (55.0, 45.0, 0.0)}                # GPSInfo
    out = process_image(make_image("JPEG", (300, 200), exif=exif))
    assert (out.width, out.height) == (200, 300)
    assert out.content_type == "image/jpeg" and out.extension == "jpg"
    assert len(Image.open(BytesIO(out.data)).getexif()) == 0

def test_long_side_is_reduced_to_2000() -> None:
    out = process_image(make_image("PNG", (4000, 1000)))
    assert (out.width, out.height, out.content_type) == (2000, 500, "image/png")

def test_small_image_is_not_upscaled() -> None:
    out = process_image(make_image("WEBP", (640, 480)))
    assert (out.width, out.height, out.extension) == (640, 480, "webp")

@pytest.mark.parametrize("payload", [
    b"<html><script>alert(1)</script></html>",
    b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
    "GIF",                                               # make_image("GIF", (10, 10))
    "TRUNCATED_JPEG",                                    # make_image("JPEG", (100, 100))[:200]
])
def test_rejects_non_allowed_or_broken_files(payload: object) -> None:
    with pytest.raises(UnsupportedImage): ...

def test_rejects_decompression_bomb() -> None:
    bomb = make_image("PNG", (7000, 7000), mode="1")     # 49 Мп, файл маленький
    with pytest.raises(FileTooLarge):
        process_image(bomb)

# tests/site_content/test_media_api.py
async def test_upload_stores_processed_file_and_row(tutor_client, minio_client, db_session) -> None:
    r = await tutor_client.post("/api/admin/media",
                                files={"file": ("photo.png", make_image("JPEG", (800, 600)), "image/png")})
    assert r.status_code == 201
    body = r.json()
    assert body["url"].startswith("/media/site/") and body["url"].endswith(".jpg")
    assert (body["width"], body["height"], body["content_type"]) == (800, 600, "image/jpeg")
    key = body["url"].removeprefix("/media/")
    assert minio_client.stat_object("media-test", key).content_type == "image/jpeg"
    assert (await db_session.get(Media, uuid.UUID(body["id"]))) is not None

async def test_upload_over_5_mb_is_413_and_nothing_stored(tutor_client, db_session) -> None:
    # файл из MAX_UPLOAD_BYTES + 1 байт → 413 file_too_large; select(count(Media)) == 0

async def test_upload_fake_jpeg_is_415(tutor_client) -> None:
    # ("photo.jpg", b"not an image", "image/jpeg") → 415 unsupported_media_type

async def test_upload_requires_tutor(client, parent_client) -> None:
    # аноним → 401 not_authenticated; родитель → 404

async def test_storage_failure_is_503_and_no_row(app, tutor_client, db_session) -> None:
    # dependency_overrides[get_media_storage] → хранилище, чей put бросает StorageUnavailable
    # → 503 storage_unavailable; count(Media) == 0

async def test_s3_storage_wraps_connection_errors(settings: Settings) -> None:
    storage = S3MediaStorage(settings.model_copy(update={"s3_endpoint_url": "http://127.0.0.1:1"}))
    with pytest.raises(StorageUnavailable):
        await storage.put("site/x.jpg", b"x", "image/jpeg")
```

Фикстуры `tutor_client` и `parent_client` (вход через `tests.factories.login`) — в `tests/site_content/conftest.py`, по образцу `tests/families/conftest.py`.

- [ ] **Step 3: Запустить — убедиться, что падают**

Run: `just test-backend tests/site_content --no-cov`
Expected: FAIL — нет `app.site_content.images` / маршрута `/api/admin/media` (404).

- [ ] **Step 4: Реализовать по Interfaces и подключить роутер в `create_app`**

- [ ] **Step 5: Запустить тесты и линтеры, сгенерировать клиент**

Run: `just test-backend`, `just lint-backend`, `just gen-api`, `just lint-frontend`
Expected: зелёное. В `endpoints/admin/admin.ts` есть `useUploadMedia`, тело запроса передаётся как `FormData`.

- [ ] **Step 6: Проверить MinIO в dev**

Run: `just dev`, затем открыть http://localhost:9001 (логин и пароль — `S3_ACCESS_KEY`/`S3_SECRET_KEY` из `.env`)
Expected: бакет `media` существует, анонимное чтение включено.

- [ ] **Step 7: Commit**

```bash
git add backend infra .env.example frontend/openapi.json frontend/src/api/generated
git commit -m "feat(backend): image upload to S3 with content sniffing, EXIF stripping and resize"
```

---

### Task 4: API блоков — `/public/site`, `/admin/site-blocks`, revalidate после сохранения

**Files:**
- Create: `backend/app/site_content/public_router.py`
- Modify: `backend/app/site_content/schemas.py`, `service.py`, `admin_router.py`, `backend/app/main.py`
- Test: `backend/tests/site_content/test_admin_blocks.py`, `backend/tests/site_content/test_public_site.py`

**Interfaces:**
- Consumes: схемы и `referenced_media_ids` из Task 2, `MediaOut`/`media_url` из Task 3, `TaskQueueDep`/`REVALIDATE_SITE_TASK` из Task 1.
- Produces:
  - **Публичные схемы:**
    - `MediaRef(BaseModel)`: `url: str`, `width: int`, `height: int`;
    - `HeroPublic`: `name`, `title`, `subtitle`, `photo: MediaRef | None`, `cta_text`;
    - `AboutPublic`: `text`, `photo: MediaRef | None`, `credentials`;
    - `ReviewPublic`: `author`, `text`, `child_age`, `photo: MediaRef | None`;
    - `ReviewsPublic`: `items: list[ReviewPublic]`;
    - `PublicSite`: `hero: HeroPublic`, `about: AboutPublic`, `services: ServicesBlock`, `reviews: ReviewsPublic`, `faq: FaqBlock`, `contacts: ContactsBlock`.
  - **Админ-схема:** `SiteBlocksAdmin`: `hero: HeroBlock`, `about: AboutBlock`, `services: ServicesBlock`, `reviews: ReviewsBlock`, `faq: FaqBlock`, `contacts: ContactsBlock`, `media: list[MediaOut]` — фото, на которые ссылаются блоки.
  - **`service`:**
    - `get_site_blocks(session: AsyncSession, settings: Settings) -> SiteBlocksAdmin`.
    - `save_block(session: AsyncSession, key: BlockKey, block: BaseModel) -> None`:
      - проверяет существование всех `referenced_media_ids` одним запросом;
      - если какого-то фото нет → `ValidationFailed("Фото не найдено — загрузите его заново", details={"fields": [{"loc": ["body", *loc], "message": "Фото не найдено", "type": "media_not_found"}, ...]})`;
      - затем делает upsert `INSERT … ON CONFLICT (key) DO UPDATE SET data = …, updated_at = now()`, где `data` берётся из `block.model_dump(mode="json")`.
    - `get_public_site(session: AsyncSession, settings: Settings) -> PublicSite`:
      - читает все 6 строк и одним запросом — все упомянутые `Media`;
      - отсутствующее фото → `photo: None`;
      - отсутствующая строка блока → `RuntimeError`, то есть 500: строки создаёт миграция, их отсутствие — ошибка развёртывания.
    - `request_site_revalidation(queue: TaskQueue) -> None` — `await queue.enqueue(REVALIDATE_SITE_TASK)`; любое исключение логируется как `site_revalidation_enqueue_failed` (warning, `exc_info`) и не пробрасывается.
  - **Admin router:**
    - `GET /admin/site-blocks` → `get_site_blocks`;
    - шесть маршрутов `PUT /admin/site-blocks/{hero|about|services|reviews|faq|contacts}` с обработчиками `update_hero_block(body: HeroBlock, ...) -> HeroBlock`, `update_about_block`, `update_services_block`, `update_reviews_block`, `update_faq_block`, `update_contacts_block`. Каждый вызывает общий `_save_and_revalidate(session, queue, key, body)`, который выполняет:
      1. `save_block`;
      2. `await session.commit()` — с комментарием: задача должна увидеть закоммиченные данные;
      3. `request_site_revalidation`.
      
      Обработчик возвращает `body` — нормализованный блок.
  - **Public router** (`prefix="/public"`, `tags=["public"]`): `GET /public/site` → `get_public_site`, без авторизации.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/site_content/test_public_site.py
async def test_public_site_returns_seeded_stubs_without_auth(client) -> None:
    r = await client.get("/api/public/site")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"hero", "about", "services", "reviews", "faq", "contacts"}
    assert body["hero"]["cta_text"] == "Записаться на пробное" and body["hero"]["photo"] is None
    assert body["reviews"] == {"items": []}

async def test_public_site_resolves_photo(client, db_session) -> None:
    media = Media(s3_key="site/a.jpg", content_type="image/jpeg", size_bytes=10, width=800, height=600)
    # сохранить hero c photo_media_id=media.id через service.save_block
    hero = (await client.get("/api/public/site")).json()["hero"]
    assert hero["photo"] == {"url": "/media/site/a.jpg", "width": 800, "height": 600}

async def test_public_site_hides_photo_whose_media_row_is_gone(client, db_session) -> None:
    # UPDATE site_blocks SET data = jsonb_set(data, '{photo_media_id}', '"<uuid7>"') WHERE key='hero'
    # → hero.photo is None, ответ 200

# tests/site_content/test_admin_blocks.py
async def test_put_hero_saves_normalized_block_and_requests_revalidation(tutor_client, task_queue) -> None:
    r = await tutor_client.put("/api/admin/site-blocks/hero", json={
        "name": "  Анна Смирнова ", "title": "Английский с удовольствием", "subtitle": "Онлайн",
        "photo_media_id": None, "cta_text": "Записаться"})
    assert r.status_code == 200 and r.json()["name"] == "Анна Смирнова"
    assert (await tutor_client.get("/api/admin/site-blocks")).json()["hero"]["name"] == "Анна Смирнова"
    assert task_queue.calls == [("site_content.revalidate_site", {})]

async def test_commit_happens_before_revalidation_is_enqueued(app, tutor_client, db_session) -> None:
    events: list[str] = []
    # обернуть db_session.commit, чтобы дописывать "commit"; FakeTaskQueue, дописывающий "enqueue"
    await tutor_client.put("/api/admin/site-blocks/faq", json={"items": []})
    assert events[:2] == ["commit", "enqueue"]

async def test_block_is_saved_even_if_enqueue_fails(app, tutor_client) -> None:
    # FakeTaskQueue(fail=True); structlog.testing.capture_logs()
    # → 200; GET показывает новые данные; в логах событие "site_revalidation_enqueue_failed"

async def test_unknown_photo_is_422_with_field_path_and_nothing_saved(tutor_client, task_queue) -> None:
    r = await tutor_client.put("/api/admin/site-blocks/reviews", json={"items": [
        {"author": "А", "text": "Т", "child_age": None, "photo_media_id": None},
        {"author": "Б", "text": "Т", "child_age": 9, "photo_media_id": str(uuid7())}]})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["details"]["fields"][0]["loc"] == ["body", "items", 1, "photo_media_id"]
    assert (await tutor_client.get("/api/admin/site-blocks")).json()["reviews"] == {"items": []}
    assert task_queue.calls == []

async def test_invalid_body_is_422_and_no_revalidation(tutor_client, task_queue) -> None:
    # PUT /hero с title="" → 422 validation_error, loc == ["body", "title"]; task_queue.calls == []

async def test_admin_blocks_list_referenced_media(tutor_client, db_session) -> None:
    # about с photo → GET /api/admin/site-blocks → media == [MediaOut этого фото]

@pytest.mark.parametrize("method,path", [("GET", "/api/admin/site-blocks"),
                                         ("PUT", "/api/admin/site-blocks/hero")])
async def test_site_blocks_are_tutor_only(client, parent_client, method, path) -> None:
    # аноним → 401, родитель → 404
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/site_content/test_admin_blocks.py tests/site_content/test_public_site.py --no-cov`
Expected: FAIL — 404 на `/api/public/site` и `/api/admin/site-blocks`.

- [ ] **Step 3: Реализовать по Interfaces, подключить `public_router` в `create_app`**

- [ ] **Step 4: Тесты, линтеры, клиент**

Run: `just test-backend`, `just lint-backend`, `just gen-api`, `just lint-frontend`
Expected: зелёное. Появились `useGetSiteBlocks`, `useUpdateHeroBlock` … `useUpdateContactsBlock` и `getPublicSite`, а в `src/api/generated/zod/public/public.ts` — схема `GetPublicSiteResponse`.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(backend): site blocks API with media checks and revalidation after commit"
```

---

### Task 5: Frontend — данные лендинга на сервере и `/api/revalidate`

**Files:**
- Create:
  - `frontend/src/lib/server-env.ts`, `frontend/src/lib/site-content.ts`;
  - `frontend/src/app/api/revalidate/route.ts`;
  - `frontend/src/test/site-fixture.ts`.
- Modify: `frontend/next.config.ts`, `frontend/.env.development`, `infra/docker-compose.yml` (env сервиса `web`).
- Test: `frontend/src/lib/site-content.test.ts`, `frontend/src/app/api/revalidate/route.test.ts`.

**Interfaces:**
- Consumes: `PublicSite` (`@/api/generated/model`), `GetPublicSiteResponse` (`@/api/generated/zod/public/public`).
- Produces:
  - `serverEnv(name: "API_INTERNAL_URL" | "SITE_URL" | "REVALIDATE_SECRET"): string` — читает `process.env` во время вызова, убирает завершающий `/`. Если переменной нет → `Error("Не задана переменная окружения NAME")`.
  - `SITE_CONTENT_TAG = "site-content"`.
  - `getSite(): Promise<PublicSite>`:
    - внутри `'use cache'`, `cacheTag(SITE_CONTENT_TAG)` и `cacheLife({ stale: 300, revalidate: 3600, expire: 86400 })`;
    - запрос `fetch(serverEnv("API_INTERNAL_URL") + "/api/public/site", { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(5000) })`;
    - ответ не 2xx → `Error("GET /api/public/site → <status>")`;
    - ответ проверяется через `GetPublicSiteResponse.parse`.
    
    Ошибки не кешируются: исключение выходит из `'use cache'`.
  - **`POST /api/revalidate`** (`app/api/revalidate/route.ts`):
    - `REVALIDATE_SECRET` не задан → 503 `{"error": {"code": "revalidate_not_configured", ...}}`;
    - заголовок `Authorization` не равен `Bearer <secret>` → 401 `{"error": {"code": "invalid_secret", ...}}`. Сравнение через `timingSafeEqual` из `node:crypto`; при разной длине — сразу 401;
    - иначе `revalidateTag(SITE_CONTENT_TAG, { expire: 0 })` → 204.
    
    Маршрут лежит в `app/`, поэтому имеет приоритет над dev-rewrite `/api/:path*`: rewrites, заданные массивом, применяются после файловых маршрутов. Снаружи он недоступен: в production nginx отправляет `/api/*` в FastAPI.
  - **`next.config.ts`:** второй rewrite `/media/:path*` → `${MEDIA_PROXY_URL}/:path*`, если `MEDIA_PROXY_URL` задан.
  - **`.env.development`:** `API_INTERNAL_URL=http://localhost:8000`, `SITE_URL=http://localhost:3000`, `MEDIA_PROXY_URL=http://localhost:9000/media`, `REVALIDATE_SECRET=dev-revalidate-secret-change-me` с комментарием «только dev; должен совпадать с REVALIDATE_SECRET в .env».
  - **Сервис `web` в compose:** `env_file: ../.env`, `environment: API_INTERNAL_URL: http://api:8000`.
  - **`siteFixture: PublicSite`** — полный пример:
    - `hero` с фото `/media/site/hero.jpg` 800×1000;
    - 2 услуги (одна с ценой 0), 2 отзыва (один с `child_age: 9`), 2 вопроса FAQ;
    - все контакты (`telegram: "anna_english"`, `whatsapp: "+79991234567"`, `phone: "+79991234567"`, `email: "anna@example.com"`, `working_hours_text: "Пн–Пт 10:00–20:00"`).

- [ ] **Step 1: Написать падающие тесты**

```ts
// src/app/api/revalidate/route.test.ts
vi.mock("next/cache", () => ({ revalidateTag: vi.fn() }));
import { revalidateTag } from "next/cache";
import { POST } from "./route";

const call = (auth?: string) =>
  POST(new Request("http://web.test/api/revalidate", {
    method: "POST", headers: auth ? { Authorization: auth } : {} }));

test("valid secret revalidates site-content immediately", async () => {
  vi.stubEnv("REVALIDATE_SECRET", "dev-revalidate-secret-change-me");
  const res = await call("Bearer dev-revalidate-secret-change-me");
  expect(res.status).toBe(204);
  expect(revalidateTag).toHaveBeenCalledWith("site-content", { expire: 0 });
});
test.each([undefined, "Bearer wrong", "dev-revalidate-secret-change-me"])(
  "rejects %s with 401", async (auth) => { /* 401, code invalid_secret, revalidateTag не вызван */ });
test("503 when secret is not configured", async () => { /* vi.stubEnv("REVALIDATE_SECRET", "") → 503 */ });

// src/lib/site-content.test.ts
vi.mock("next/cache", () => ({ cacheTag: vi.fn(), cacheLife: vi.fn() }));
test("fetches public site from internal API and tags the cache", async () => {
  vi.stubEnv("API_INTERNAL_URL", "http://api.test/");
  const fetchMock = vi.fn(async () => Response.json(siteFixture));
  vi.stubGlobal("fetch", fetchMock);
  await expect(getSite()).resolves.toEqual(siteFixture);
  expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/public/site");
  expect(cacheTag).toHaveBeenCalledWith("site-content");
});
test("throws on error status", async () => { /* Response 500 → rejects /→ 500/ */ });
test("throws on unexpected shape", async () => { /* Response.json({hero: {}}) → rejects */ });
test("throws when API_INTERNAL_URL is missing", async () => { /* /API_INTERNAL_URL/ */ });
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend test -- src/lib/site-content.test.ts src/app/api/revalidate`
Expected: FAIL — модули не найдены.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-frontend`, `just lint-frontend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend infra/docker-compose.yml
git commit -m "feat(frontend): cached server-side site content and secret-protected revalidate route"
```

---

### Task 6: Frontend — лендинг

**Files:**
- Create:
  - `frontend/src/components/site/landing.tsx`, `site-header.tsx`, `site-footer.tsx`;
  - `frontend/src/components/site/hero-section.tsx`, `about-section.tsx`, `services-section.tsx`, `reviews-section.tsx`, `faq-section.tsx`, `trial-section.tsx`, `contacts-section.tsx`;
  - `frontend/src/components/site/contact-links.tsx`, `markdown.tsx`;
  - `frontend/src/lib/site-format.ts`, `frontend/src/app/error.tsx`.
- Modify: `frontend/src/app/page.tsx`, `frontend/package.json`, `pnpm-lock.yaml`.
- Delete: `frontend/src/app/page.test.tsx` — заменяется тестами `landing.test.tsx`.
- Test: `frontend/src/components/site/landing.test.tsx`, `markdown.test.tsx`, `frontend/src/lib/site-format.test.ts`.

**Interfaces:**
- Consumes: `getSite`, `siteFixture`, `PublicSite`.
- Produces:
  - **`site-format.ts`:**
    - `formatRub(value: number): string`: `0` → «Бесплатно», иначе `Intl.NumberFormat("ru-RU")` + « ₽»;
    - `pluralRu(n: number, forms: [string, string, string]): string`;
    - `type ContactLink = { kind: "telegram" | "whatsapp" | "phone" | "email"; label: string; href: string }`;
    - `contactLinks(contacts: ContactsBlock): ContactLink[]` — порядок telegram, whatsapp, phone, email:
      - `https://t.me/{telegram}` (label `@{telegram}`);
      - `https://wa.me/{цифры}` (label «WhatsApp»);
      - `tel:{phone}`;
      - `mailto:{email}`.
  - **`Markdown({ children }: { children: string })`** — `react-markdown` без `rehype-raw`, ссылки с `rel="noopener noreferrer"`. Стандартный `urlTransform` убирает `javascript:`.
  - **`Landing({ site }: { site: PublicSite })`** — синхронный презентационный компонент. Порядок и якоря:
    1. `SiteHeader`: имя `hero.name`, навигация по присутствующим секциям (скрыта < md), кнопка `hero.cta_text` → `#trial`;
    2. `HeroSection`: заголовок, подзаголовок, фото через `next/image` с `unoptimized`, `width`/`height` из `MediaRef`, `alt={hero.name}`, `priority`;
    3. `#about`;
    4. `#services` — карточки: название, описание, «60 мин · Онлайн», `formatRub`;
    5. `#reviews` — автор и «ребёнку N лет» через `pluralRu`;
    6. `#faq` — `<details>/<summary>`;
    7. `#trial` — временная секция до плана 4: «Напишите удобным способом — договоримся о времени пробного занятия» и `ContactLinks`. Если контактов нет — «Контакты скоро появятся»;
    8. `#contacts` — `ContactLinks` + `working_hours_text`;
    9. `SiteFooter`: ссылки «Политика обработки персональных данных» → `/privacy` и «Вход для учеников» → `/login`.
    
    Пустые `services`, `reviews`, `faq` и контакты, где всё `null`, — секция и пункт навигации не выводятся. Вёрстка mobile-first, контейнер `max-w-5xl`, шапка `sticky`.
  - **`app/page.tsx`:**
    ```tsx
    export default function Home() {
      return <Suspense fallback={<LandingSkeleton />}><LandingContent /></Suspense>;
    }
    async function LandingContent() {
      await connection();            // данные и env — только во время запроса: build не ходит в API
      return <Landing site={await getSite()} />;
    }
    ```
  - **`app/error.tsx`** — клиентский компонент «Не удалось загрузить страницу» с кнопкой «Попробовать снова» (`reset()`).

- [ ] **Step 1: Установить react-markdown**

Run: `pnpm --dir frontend add react-markdown`
Expected: зависимость в `package.json`, lockfile обновлён.

- [ ] **Step 2: Написать падающие тесты**

```tsx
// src/lib/site-format.test.ts
test.each([[0, "Бесплатно"], [1500, /^1\s500\s₽$/], [100000, /^100\s000\s₽$/]])(
  "formatRub(%s)", (v, expected) => { /* toMatch / toBe */ });
test.each([[1, "год"], [3, "года"], [5, "лет"], [11, "лет"], [18, "лет"], [21, "год"], [22, "года"]])(
  "pluralRu(%s)", (n, form) => expect(pluralRu(n, ["год", "года", "лет"])).toBe(form));
test("contactLinks builds hrefs in fixed order", () => {
  expect(contactLinks(siteFixture.contacts).map((l) => l.href)).toEqual([
    "https://t.me/anna_english", "https://wa.me/79991234567", "tel:+79991234567", "mailto:anna@example.com"]);
});
test("contactLinks skips nulls", () => { /* только email → один элемент */ });

// src/components/site/markdown.test.tsx
test("renders markdown but never raw HTML or javascript: links", () => {
  const { container } = render(
    <Markdown>{"**Привет**<script>alert(1)</script><img src=x onerror=alert(1)> [x](javascript:alert(1))"}</Markdown>);
  expect(container.querySelector("strong")).toHaveTextContent("Привет");
  expect(container.querySelector("script, img")).toBeNull();
  expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
});

// src/components/site/landing.test.tsx
test("renders sections in order with anchors", () => {
  render(<Landing site={siteFixture} />);
  const ids = [...document.querySelectorAll("main section[id]")].map((s) => s.id);
  expect(ids).toEqual(["about", "services", "reviews", "faq", "trial", "contacts"]);
  expect(screen.getByRole("link", { name: siteFixture.hero.cta_text })).toHaveAttribute("href", "#trial");
  expect(screen.getByRole("img", { name: siteFixture.hero.name })).toHaveAttribute("width", "800");
});
test("hides empty sections and their nav links", () => {
  const site = { ...siteFixture, reviews: { items: [] }, faq: { items: [] },
    contacts: { telegram: null, whatsapp: null, phone: null, email: null, working_hours_text: null } };
  render(<Landing site={site} />);
  expect(screen.queryByRole("heading", { name: "Отзывы" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Отзывы" })).toBeNull();
  expect(document.getElementById("contacts")).toBeNull();
  expect(screen.getByText("Контакты скоро появятся")).toBeInTheDocument();
});
test("service shows duration, format and free price", () => { /* «30 мин · Онлайн», «Бесплатно» */ });
test("review shows child age with correct plural", () => { /* «ребёнку 9 лет» */ });
test("footer links to privacy policy and login", () => { /* href /privacy и /login */ });
```

- [ ] **Step 3: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend test -- src/components/site src/lib/site-format.test.ts`
Expected: FAIL — модули не найдены.

- [ ] **Step 4: Реализовать по Interfaces**

- [ ] **Step 5: Проверить, включая сборку без API**

Run: `just test-frontend`, `just lint-frontend`, затем при остановленном backend (`just down`) — `pnpm --dir frontend build`
Expected: тесты зелёные. Сборка проходит, `/` в выводе помечен как частично или полностью динамический, ошибок «fetch failed» нет.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): server-rendered landing built from site content blocks"
```

---

### Task 7: Frontend — SEO и `/privacy`

**Files:**
- Create:
  - `frontend/src/lib/seo.ts`;
  - `frontend/src/app/robots.ts`, `frontend/src/app/sitemap.ts`;
  - `frontend/src/app/privacy/page.tsx`, `frontend/src/components/site/privacy-policy.tsx`.
- Modify:
  - `frontend/src/app/page.tsx` — `generateMetadata`, JSON-LD;
  - `frontend/src/app/cabinet/layout.tsx`, `frontend/src/app/admin/layout.tsx`;
  - серверные `page.tsx` в `login`, `invite/[token]`, `reset/[token]` — добавить `robots: { index: false, follow: false }`.
- Test: `frontend/src/lib/seo.test.ts`, `frontend/src/app/robots.test.ts`, `frontend/src/app/sitemap.test.ts`, `frontend/src/components/site/privacy-policy.test.tsx`.

**Interfaces:**
- Consumes: `getSite`, `serverEnv("SITE_URL")`, `siteFixture`, `contactLinks`, `SiteHeader`/`SiteFooter`.
- Produces:
  - **`buildMetadata(site: PublicSite, siteUrl: string): Metadata`:**
    - `metadataBase: new URL(siteUrl)`;
    - `title: \`${hero.name} — ${hero.title}\``, `description: hero.subtitle`;
    - `alternates: { canonical: "/" }`;
    - `openGraph: { type: "website", locale: "ru_RU", url: "/", title, description, images: hero.photo ? [{ url: hero.photo.url, width, height }] : undefined }`.
  - **`buildJsonLd(site: PublicSite, siteUrl: string): Record<string, unknown>[]`:**
    - `Person`: `@context: "https://schema.org"`, `name`, `jobTitle: "Репетитор по английскому языку"`, `description`, `url: siteUrl`, `image` (абсолютный URL), `email`, `telephone`, `sameAs: [t.me-ссылка]` (пустые поля опускаются);
    - по одному `Service` на каждую услугу: `name`, `description`, `serviceType: "Репетиторство по английскому языку"`, `provider: { "@type": "Person", name }`, `offers: { "@type": "Offer", price: String(price_rub), priceCurrency: "RUB" }`.
  - **`jsonLdScript(data: unknown): string`** — `JSON.stringify(data).replace(/</g, "\\u003c")`.
  - **`app/page.tsx`:**
    - `export async function generateMetadata()` — `await connection()`, затем `buildMetadata(await getSite(), serverEnv("SITE_URL"))`;
    - в `LandingContent` добавить `<script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(buildJsonLd(...)) }} />`.
  - **`robots()`** (async, первым делом `await connection()`): `{ rules: [{ userAgent: "*", allow: "/", disallow: ["/admin", "/cabinet", "/invite", "/reset", "/login", "/api"] }], sitemap: \`${siteUrl}/sitemap.xml\` }`.
  - **`sitemap()`** (async, `await connection()`): `[{ url: \`${siteUrl}/\`, changeFrequency: "monthly", priority: 1 }, { url: \`${siteUrl}/privacy\`, changeFrequency: "yearly", priority: 0.3 }]`.
  - **`PrivacyPolicy({ operatorName, contacts }: { operatorName: string; contacts: ContactsBlock })`** — h1 «Политика обработки персональных данных» и разделы:
    1. оператор — `operatorName`;
    2. какие данные собираются:
       - заявка: имя родителя, имя и возраст ребёнка, телефон или мессенджер, комментарий, UTM-метки;
       - кабинет: ФИО, email и телефон родителя; имя, год рождения, уровень и логин ребёнка; расписание и заметки;
    3. цели: связь по заявке, проведение занятий, доступ к кабинету;
    4. основание — согласие; данные ребёнка — с согласия законного представителя;
    5. хранение: серверы в РФ; заявки, не ставшие учениками, обезличиваются через 12 месяцев; данные семьи хранятся до отзыва согласия и удаляются по запросу;
    6. передача: третьим лицам не передаются; краткое уведомление о новой заявке (имя, возраст ребёнка, способ связи) репетитор получает в Telegram;
    7. cookie: только технические (сессия входа, защита от CSRF), аналитики нет;
    8. права субъекта и отзыв согласия — через контакты оператора (`contactLinks(contacts)`; если контактов нет — «через форму на сайте»).
  - **`app/privacy/page.tsx`:** `metadata = { title: "Политика обработки персональных данных", alternates: { canonical: "/privacy" } }`. Тот же паттерн `Suspense` + `connection()` + `getSite()` → `SiteHeader`, `PrivacyPolicy`, `SiteFooter`.

- [ ] **Step 1: Написать падающие тесты**

```ts
// src/lib/seo.test.ts
test("metadata uses hero and absolute og image", () => {
  const m = buildMetadata(siteFixture, "https://anna.example");
  expect(m.title).toBe(`${siteFixture.hero.name} — ${siteFixture.hero.title}`);
  expect(m.description).toBe(siteFixture.hero.subtitle);
  expect(m.metadataBase?.toString()).toBe("https://anna.example/");
  expect(m.openGraph?.images).toEqual([{ url: "/media/site/hero.jpg", width: 800, height: 1000 }]);
});
test("json-ld has a Person and one Service per item", () => {
  const [person, ...services] = buildJsonLd(siteFixture, "https://anna.example");
  expect(person).toMatchObject({ "@type": "Person", name: siteFixture.hero.name,
    image: "https://anna.example/media/site/hero.jpg", sameAs: ["https://t.me/anna_english"] });
  expect(services).toHaveLength(2);
  expect(services[0]).toMatchObject({ "@type": "Service", offers: { priceCurrency: "RUB" } });
});
test("json-ld script cannot close the script tag", () => {
  const out = jsonLdScript(buildJsonLd(
    { ...siteFixture, hero: { ...siteFixture.hero, name: "</script><script>alert(1)</script>" } }, "https://a.example"));
  expect(out).not.toContain("</script>");
  expect(JSON.parse(out)[0].name).toBe("</script><script>alert(1)</script>");
});

// src/app/robots.test.ts  (vi.mock("next/server", () => ({ connection: vi.fn() })); vi.stubEnv("SITE_URL", "https://anna.example"))
test("robots closes private zones and points to sitemap", async () => {
  expect(await robots()).toEqual({ rules: [{ userAgent: "*", allow: "/",
    disallow: ["/admin", "/cabinet", "/invite", "/reset", "/login", "/api"] }],
    sitemap: "https://anna.example/sitemap.xml" });
});
// src/app/sitemap.test.ts — URL ровно ["https://anna.example/", "https://anna.example/privacy"]

// src/components/site/privacy-policy.test.tsx
test("policy names the operator, retention, Telegram and contacts", () => {
  render(<PrivacyPolicy operatorName="Анна Смирнова" contacts={siteFixture.contacts} />);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Политика обработки персональных данных");
  expect(screen.getByText(/Анна Смирнова/)).toBeInTheDocument();
  expect(screen.getByText(/12 месяцев/)).toBeInTheDocument();
  expect(screen.getByText(/Telegram/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "anna@example.com" })).toHaveAttribute("href", "mailto:anna@example.com");
});
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend test -- src/lib/seo.test.ts src/app/robots.test.ts src/app/sitemap.test.ts src/components/site/privacy-policy.test.tsx`
Expected: FAIL — модули не найдены.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить, включая сборку без API**

Run: `just test-frontend`, `just lint-frontend`, `pnpm --dir frontend build` (backend остановлен)
Expected: зелёное. Сборка проходит; `/`, `/privacy`, `/robots.txt` и `/sitemap.xml` не требуют API и env во время сборки.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): SEO metadata, JSON-LD, robots, sitemap and privacy policy"
```

---

### Task 8: Frontend — редактор сайта: страница, hero/about/contacts, загрузка фото

**Files:**
- Create:
  - `frontend/src/app/admin/site/page.tsx`, `site-editor.tsx`;
  - `frontend/src/app/admin/site/hero-editor.tsx`, `about-editor.tsx`, `contacts-editor.tsx`, `photo-field.tsx`.
- Modify: `frontend/src/app/admin/admin-shell.tsx` (пункт меню «Сайт» → `/admin/site`), `frontend/src/lib/api-fetch.test.ts`.
- Test: `frontend/src/app/admin/site/hero-editor.test.tsx`, `photo-field.test.tsx`, `contacts-editor.test.tsx`, `about-editor.test.tsx`.

**Interfaces:**
- Consumes:
  - хуки `useGetSiteBlocks`, `getGetSiteBlocksQueryKey`, `useUpdateHeroBlock`, `useUpdateAboutBlock`, `useUpdateContactsBlock`, `useUploadMedia`;
  - zod-схемы `UpdateHeroBlockBody`, `UpdateAboutBlockBody`, `UpdateContactsBlockBody`;
  - `Markdown`, `applyApiErrors`, `errorMessage`.
- Produces:
  - **`page.tsx`** — по образцу `admin/families/page.tsx` (`export const instant = false`), рендерит `SiteEditor`.
  - **`SiteEditor`:**
    - загружает `useGetSiteBlocks`;
    - вверху ссылка «Открыть сайт» (`href="/"`, `target="_blank"`, `rel="noopener noreferrer"`);
    - ниже карточки редакторов в порядке лендинга. Каждый редактор получает `block` и `media: MediaOut[]`;
    - пока данные грузятся — скелетон; при ошибке — `errorMessage`.
  - **Общее поведение редактора:**
    - `useForm` с `zodResolver(<Generated>Body)`, `defaultValues` из блока;
    - после успеха — `toast.success("Сохранено. Сайт обновится в течение минуты")` и `invalidateQueries(getGetSiteBlocksQueryKey())`;
    - ошибки 422 раскладываются по полям через `applyApiErrors`, остальные показываются в `Alert`;
    - кнопка «Сохранить» заблокирована, пока запрос выполняется.
  - **`PhotoField({ label, value, media, onChange }: { label: string; value: string | null; media: MediaOut[]; onChange: (id: string | null) => void })`:**
    - превью — из `media` по `value` либо из только что загруженного `MediaOut`;
    - `<input type="file" accept="image/jpeg,image/png,image/webp">`;
    - файл больше 5 МБ → сообщение «Файл больше 5 МБ» без запроса;
    - иначе `useUploadMedia` → `onChange(created.id)`;
    - ошибки API показываются через `errorMessage`;
    - кнопка «Убрать фото» → `onChange(null)`.
  - **`AboutEditor`:** `textarea` для `text` и переключатель «Предпросмотр», который рендерит `Markdown`. `credentials` — список строк: добавить, удалить, не больше 20.
  - **`ContactsEditor`:** пустые поля отправляются как `null`, значения из ответа сервера (уже нормализованные) возвращаются в форму через `reset(saved)`.

- [ ] **Step 1: Написать падающие тесты**

Мок `fetch` — по образцу `families-list.test.tsx`; `QueryClientProvider` с новым клиентом в каждом тесте.

```tsx
// src/lib/api-fetch.test.ts — добавить
test("FormData body is sent without forcing Content-Type", async () => {
  // fetch-мок; apiFetch("/api/admin/media", { method: "POST", body: formData })
  // → headers не содержат Content-Type (его выставит браузер с boundary), X-CSRF-Token есть
});

// hero-editor.test.tsx
test("submits edited hero and reports success", async () => {
  // render(<HeroEditor block={hero} media={[]} />); очистить «Заголовок», ввести «Новый заголовок»; «Сохранить»
  // → PUT /api/admin/site-blocks/hero, JSON-тело с title «Новый заголовок»; toast «Сохранено…»
});
test("server field errors land on fields", async () => {
  // ответ 422 {error:{code:"validation_error", details:{fields:[{loc:["body","title"], message:"Слишком длинно"}]}}}
  // → под полем «Заголовок» текст «Слишком длинно»
});

// photo-field.test.tsx
test("uploads selected file and shows preview", async () => {
  // userEvent.upload(input, new File([...], "a.png", {type:"image/png"}))
  // → POST /api/admin/media с FormData (body instanceof FormData, поле file);
  //   ответ MediaOut{url:"/media/site/x.png"} → onChange("m1"), img src="/media/site/x.png"
});
test("rejects files over 5 MB without a request", async () => { /* текст «Файл больше 5 МБ», fetch не вызван */ });
test("shows API error from upload", async () => { /* 415 → текст из error.message */ });
test("remove clears the photo", async () => { /* «Убрать фото» → onChange(null) */ });

// contacts-editor.test.tsx
test("empty fields are sent as null", async () => {
  // очистить telegram → тело PUT {telegram: null, ...}
});

// about-editor.test.tsx
test("preview renders markdown", async () => { /* ввести "**жирный**" → «Предпросмотр» → <strong>жирный</strong> */ });
test("credentials can be added and removed", async () => { /* «Добавить» → новое поле; «Удалить» → убрано; тело PUT */ });
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend test -- src/app/admin/site src/lib/api-fetch.test.ts`
Expected: FAIL — модули редакторов не найдены. Тест FormData проходит сразу, если `apiFetch` уже не трогает `Content-Type`; это нормально, тест фиксирует поведение.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-frontend`, `just lint-frontend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): admin site editor for hero, about and contacts with photo upload"
```

---

### Task 9: Frontend — редакторы списков: услуги, отзывы, FAQ

**Files:**
- Create: `frontend/src/app/admin/site/services-editor.tsx`, `reviews-editor.tsx`, `faq-editor.tsx`, `list-controls.tsx`
- Modify: `frontend/src/app/admin/site/site-editor.tsx`
- Test: `frontend/src/app/admin/site/services-editor.test.tsx`, `reviews-editor.test.tsx`, `faq-editor.test.tsx`

**Interfaces:**
- Consumes: всё из Task 8, хуки `useUpdateServicesBlock`, `useUpdateReviewsBlock`, `useUpdateFaqBlock` и соответствующие zod-схемы `Update*BlockBody`.
- Produces:
  - **`ListControls({ index, count, onMoveUp, onMoveDown, onRemove })`** — кнопки «Выше», «Ниже», «Удалить» с `aria-label`, в которых есть номер элемента (`«Удалить отзыв 2»`). На краях списка кнопка перемещения заблокирована.
  - **Общее для трёх редакторов:**
    - `useFieldArray({ name: "items" })`;
    - кнопка «Добавить …» с пустым элементом;
    - кнопка блокируется на максимуме: 20 услуг, 30 отзывов, 30 вопросов;
    - числовые поля — `type="number"` с `valueAsNumber`;
    - пустой `child_age` → `null`.
  - **`ReviewsEditor`** — у каждого отзыва свой `PhotoField`.
  - **Серверные ошибки.** Ошибки с вложенным `loc` (`["body", "items", 1, "photo_media_id"]`) не ложатся на поле формы. Их сообщение показывается в `Alert` формы: для этого бэкенд в Task 4 задаёт понятный `message`.

- [ ] **Step 1: Написать падающие тесты**

```tsx
// services-editor.test.tsx
test("adds, edits and saves a service", async () => {
  // «Добавить услугу» → заполнить название, длительность 60, цену 2000, формат «Онлайн»; «Сохранить»
  // → тело PUT: items[1] == {title, description: "", duration_min: 60, price_rub: 2000, format: "Онлайн"}
});
test("moves and removes items", async () => {
  // 2 услуги; «Ниже» у первой → порядок в теле PUT поменялся; «Удалить услугу 1» → осталась одна
});
test("add button is disabled at 20 items", () => { /* 20 элементов → кнопка disabled */ });

// reviews-editor.test.tsx
test("empty child age is sent as null", async () => { /* очистить возраст → items[0].child_age === null */ });
test("unknown photo error is shown on the form", async () => {
  // 422 с message «Фото не найдено — загрузите его заново» и loc [..., 1, "photo_media_id"] → Alert с этим текстом
});

// faq-editor.test.tsx
test("saves questions in order", async () => { /* добавить вопрос, «Выше» → порядок в теле PUT */ });
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend test -- src/app/admin/site`
Expected: FAIL — модули не найдены.

- [ ] **Step 3: Реализовать по Interfaces и добавить три карточки в `SiteEditor`**

- [ ] **Step 4: Проверить**

Run: `just test-frontend`, `just lint-frontend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): list editors for services, reviews and FAQ"
```

---

### Task 10: Сквозная проверка и документация

**Files:**
- Modify: `README.md` (раздел про worker, MinIO, revalidate, новые переменные), `.env.example` (финальная сверка), `frontend/README.md` (env Next), `docs/superpowers/plans/2026-10-11-02-auth-families.md` не трогать.

**Interfaces:**
- Consumes: всё из Task 1–9.
- Produces:
  - **README:**
    - схема обновления лендинга: «сохранение → задача → `POST /api/revalidate` → тег `site-content`»;
    - `just restart worker` после правки задач;
    - MinIO console http://localhost:9001;
    - перед production заполнить `hero.name` и `contacts` — они попадают в `/privacy`;
    - `REVALIDATE_SECRET` одинаковый у backend и web.

- [ ] **Step 1: Полный прогон**

Run: `just lint`, `just test`
Expected: всё зелёное, покрытие backend ≥ 85%.

- [ ] **Step 2: Сборка без API**

Run: `just down`, затем `pnpm --dir frontend build`
Expected: сборка успешна.

- [ ] **Step 3: Ручная проверка во встроенном браузере** (`just dev`, `just web`, вход `tutor@example.com`)

Expected:
1. `/` показывает заглушки из миграции. В `view-source` есть `<script type="application/ld+json">`, `<title>` и `og:*`.
2. В `/admin/site` поменять `hero.name` и заголовок, загрузить фото, сохранить. Через несколько секунд обновлённая `/` показывает новые данные и фото (картинка идёт через `/media/...`). В `just logs worker` есть `task_started` и `task_finished` с тем же `request_id`, что в логе api.
3. Добавить отзыв, удалить вопрос FAQ — лендинг отражает изменения. Пустые секции скрыты.
4. Остановить Next, сохранить блок. В логах worker видны повторы с растущей паузой; после запуска Next очередной повтор проходит.
5. `/robots.txt` и `/sitemap.xml` используют `SITE_URL`. `/privacy` показывает имя из hero и контакты.
6. На ширине 375 px нет горизонтальной прокрутки, кнопка «Записаться на пробное» в шапке ведёт к `#trial`.

- [ ] **Step 4: Commit**

```bash
git add README.md .env.example frontend/README.md
git commit -m "docs: site content, worker, MinIO and revalidation setup"
```
