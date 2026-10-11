# План 2 из 7: `auth` + `families` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вход и выход по cookie-сессии в Redis, CSRF, rate limit, приглашения родителей, ссылки сброса пароля, учётные записи детей; админ-API и UI для семей и детей; каркас кабинета (родитель/ребёнок) и админки (репетитор); страницы `/login`, `/invite/[token]`, `/reset/[token]`.

**Architecture:** Backend — новые модули `app/families` (семьи, родители, дети, `family_scope`, админ- и кабинет-роутеры) и расширение `app/auth` (сессии, CSRF, rate limit, приглашения, сбросы, `/auth/*`). `families.service` импортирует только `auth.models/passwords/identity/sessions`; `auth.service` импортирует `families.service` — циклов нет. Frontend — клиентские страницы на сгенерированных orval-хуках; `apiFetch` сам добавляет CSRF-заголовок; `src/proxy.ts` перенаправляет без cookie на `/login`; реальная авторизация — только на backend.

**Tech Stack:** как в плане 1 + react-hook-form, @hookform/resolvers, компоненты shadcn (input, label, card, alert, badge, dialog, table, select, checkbox, textarea, sonner).

**Spec:** `docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md` — разделы 2.4–2.5, 3.1, 4.2–4.4 (только семьи/дети/пользователи/приглашения/сбросы; `/me/lessons*` — план 5), 4.5 п.4, 5.1 (страницы входа, кабинета, `/admin`, `/admin/families*`), 5.2, 6.1–6.3, 7.1, 9 п.2.

**Предыдущий план:** `docs/superpowers/plans/2026-10-11-01-foundation.md` (выполнен; код в `main`).

## Global Constraints

- Все ограничения плана 1 действуют (Python 3.12, `/api`, UUIDv7, `timestamptz`, формат ошибок, русские тексты, ruff/mypy strict/eslint/tsc, покрытие ≥ 85%, коммиты с `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`).
- Эндпоинты, которые пишут в БД, получают сессию только через `app.core.db.DbSession` (не `Depends(get_db_session)`).
- Каждая задача, меняющая API backend, заканчивается `just gen-api` и коммитом `frontend/openapi.json` + `frontend/src/api/generated/**`.
- Сессия: cookie `session`, `HttpOnly; Secure; SameSite=Lax; Path=/`; Redis `session:{sha256(token)}` → `{user_id, role, created_at}`; плавающий TTL: 7 дней `tutor`, 30 дней `parent`/`child`; индекс `user_sessions:{user_id}`.
- CSRF: cookie `csrf_token` (не HttpOnly) + заголовок `X-CSRF-Token` для всех не-`GET/HEAD/OPTIONS` под `/api/`; несовпадение → 403 `csrf_failed`.
- Rate limit входа: 5 неудачных попыток за 15 минут на пару «логин + IP», 30 неудачных на IP → 429 `rate_limited` с заголовком `Retry-After`.
- Пароль: длина ≥ 8 (ребёнок ≥ 6), ≤ 128, не из списка распространённых; argon2id.
- Одноразовые токены: `secrets.token_urlsafe(32)`, в БД только SHA-256 hex; приглашение живёт 7 дней, сброс — 24 часа.
- Недоступный объект вне своей семьи → 404; `/admin/*` для не-репетитора → 404; без сессии → 401 `not_authenticated`.
- Роутеры импортируют сервисы модулем (`from app.auth import service`, `from app.families import service as families_service`): имена обработчиков (`accept_invitation`, `reset_password`, `change_password`, …) совпадают с именами сервисных функций и задают operationId.
- Страницы Next с `useParams`/`useSearchParams` рендерят клиентский компонент внутри `<Suspense>` (требование `cacheComponents` в Next 16.4). Защита маршрутов — `src/proxy.ts` (`middleware` в 16.x переименован в `proxy`).

## Review Focus

1. **Подбор пароля** — 6-я неверная попытка за 15 минут для пары «логин + IP» → 429 с `Retry-After`, даже если 6-я попытка с верным паролем; другой логин с того же IP при этом пускает. Тест в Task 7.
2. **Повторное использование одноразовых ссылок** — принятое, просроченное или перевыпущенное приглашение и использованная ссылка сброса → 404 `invitation_invalid` / `reset_invalid`, без создания второго аккаунта. Тесты в Task 8.
3. **Доступ к чужой семье** — родитель семьи A через `/me/children/{id_ребёнка_B}/account` → 404; ребёнок → 404 на `POST /me/children/{id}/account`; родитель на любой `/admin/*` → 404. Тесты в Task 9 и Task 10.
4. **Старая cookie после смены пароля, сброса, деактивации или архивации семьи** → следующий запрос 401. Тесты в Task 8 и Task 9.
5. **Открытый редирект через `?next=`** (`//evil.com`, `https://evil.com`, `/\evil.com`) после входа → игнорируется, переход на домашнюю страницу роли. Тест в Task 13.

---

## Структура файлов

```
backend/app/
├── main.py                         # + operation id = route.name, CSRF middleware, роутеры
├── cli.py                          # + понятные ошибки create-tutor
├── core/
│   ├── config.py                   # + public_base_url, session_cookie_secure
│   ├── errors.py                   # + ErrorResponse, API_ERROR_RESPONSES, NotAuthenticated, RateLimited
│   ├── health.py                   # access-лог health → DEBUG (request_id.py)
│   ├── redis.py                    # + get_redis, RedisClient
│   ├── csrf.py                     # CsrfMiddleware, router GET /auth/csrf
│   └── rate_limit.py               # RateLimit, RateLimiter
├── auth/
│   ├── models.py                   # + Invitation, PasswordReset
│   ├── passwords.py                # + список распространённых, лимиты длины
│   ├── common_passwords.txt
│   ├── tokens.py                   # new_token(), hash_token(), TTL
│   ├── sessions.py                 # SessionStore, SessionData, cookie helpers
│   ├── deps.py                     # CurrentUser, TutorUser, ParentUser, FamilyMember
│   ├── schemas.py
│   ├── service.py                  # + authenticate, build_me, invitations, resets, change_password
│   └── router.py                   # /auth/*
├── families/
│   ├── models.py                   # Family, ParentProfile, Child, EnglishLevel
│   ├── schemas.py
│   ├── service.py
│   ├── scope.py                    # FamilyScope, FamilyScopeDep
│   ├── admin_router.py             # /admin/families*, /admin/children*, /admin/users*
│   └── cabinet_router.py           # /me/children*
migrations/versions/0002_families_auth_tokens.py
backend/tests/
├── conftest.py                     # + open_client(), flush Redis, https base_url
├── factories.py                    # make_tutor/make_family/make_parent/make_child, login()
├── core/  test_openapi.py  test_csrf.py  test_rate_limit.py
├── auth/  test_sessions.py  test_login.py  test_invitations.py  test_password_resets.py  test_change_password.py
└── families/  test_models.py  test_admin_families.py  test_admin_children.py  test_admin_users.py  test_cabinet.py

frontend/src/
├── proxy.ts
├── lib/  api-fetch.ts  query-client.ts  auth.ts  form-errors.ts  (+ *.test.ts)
├── components/ui/…                 # shadcn
├── components/  app-header.tsx  logout-button.tsx  copy-link-card.tsx  password-field.tsx
└── app/
    ├── login/  page.tsx  login-form.tsx  login-form.test.tsx
    ├── invite/[token]/  page.tsx  accept-invitation.tsx  accept-invitation.test.tsx
    ├── reset/[token]/  page.tsx  reset-password.tsx
    ├── cabinet/  layout.tsx  page.tsx  children/page.tsx  settings/page.tsx  (+ *-client.tsx)
    └── admin/  layout.tsx  page.tsx  families/page.tsx  families/[id]/page.tsx  (+ компоненты)
```

---

### Task 1: Гигиена OpenAPI и мелочи плана 1

**Files:**
- Modify: `backend/app/main.py`, `backend/app/core/errors.py`, `backend/app/core/health.py`, `backend/app/core/request_id.py`, `.github/workflows/ci.yml`
- Create: `backend/tests/core/test_openapi.py`
- Regenerate: `frontend/openapi.json`, `frontend/src/api/generated/**`

**Interfaces:**
- Produces:
  - `create_app` передаёт в `FastAPI(generate_unique_id_function=lambda route: route.name)`; имена функций-обработчиков уникальны во всём приложении (orval-хуки: `useHealth`, `useReady`, позже `useLogin`, …).
  - `app.core.errors.ErrorDetail(BaseModel)`: `code: str`, `message: str`, `details: dict[str, Any] = {}`; `ErrorResponse(BaseModel)`: `error: ErrorDetail`.
  - `app.core.errors.API_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {"4XX": {"model": ErrorResponse, "description": "Ошибка в едином формате"}}` — передаётся в `APIRouter(responses=...)` каждого роутера (FastAPI тогда не добавляет `HTTPValidationError`).
  - `RequestIdMiddleware` пишет access-лог для путей `/api/health` и `/api/health/ready` уровнем DEBUG, остальные — INFO.
  - CI: `astral-sh/setup-uv` с `version: "0.13.0"`; проверка дрейфа — `test -z "$(git status --porcelain -- frontend/openapi.json frontend/src/api/generated)"`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/core/test_openapi.py
def test_operation_ids_are_route_names(app):
    spec = app.openapi()
    assert spec["paths"]["/api/health"]["get"]["operationId"] == "health"
    assert spec["paths"]["/api/health/ready"]["get"]["operationId"] == "ready"

def test_error_schema_is_documented_instead_of_http_validation_error(app):
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert set(schemas["ErrorResponse"]["properties"]) == {"error"}
    ref = spec["paths"]["/api/health"]["get"]["responses"]["4XX"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/ErrorResponse")

# tests/core/test_request_id.py — добавить
async def test_health_access_log_is_debug(client, capsys):
    configure_logging("INFO", json=True)
    await client.get("/api/health")
    assert "http_request" not in capsys.readouterr().out
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/core/test_openapi.py tests/core/test_request_id.py --no-cov`
Expected: FAIL — `operationId == "health_api_health_get"`, нет `ErrorResponse`, лог health на INFO.

- [ ] **Step 3: Реализовать по Interfaces; `health.router = APIRouter(tags=["health"], responses=API_ERROR_RESPONSES)`**

- [ ] **Step 4: Сгенерировать клиент и проверить**

Run: `just gen-api`, `just lint`, `just test`
Expected: всё зелёное; в `frontend/src/api/generated/endpoints/health/health.ts` есть `useHealth` и `useReady`.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated .github
git commit -m "refactor(api): readable operation ids and documented error schema"
```

---

### Task 2: Политика паролей и понятные ошибки `create-tutor`

**Files:**
- Create: `backend/app/auth/common_passwords.txt`
- Modify: `backend/app/auth/passwords.py`, `backend/app/cli.py`, `backend/tests/auth/test_passwords.py`, `backend/tests/auth/test_cli.py`

**Interfaces:**
- Produces (`app.auth.passwords`):
  - `PASSWORD_MIN_LENGTH = 8`, `CHILD_PASSWORD_MIN_LENGTH = 6`, `PASSWORD_MAX_LENGTH = 128`.
  - `COMMON_PASSWORDS: frozenset[str]` — строки `common_passwords.txt` в нижнем регистре (UTF-8, по одному на строку, `#` — комментарий).
  - `validate_password(password: str, *, min_length: int = PASSWORD_MIN_LENGTH) -> None` — по порядку: короче `min_length` → `password_too_short` (как в плане 1); длиннее 128 → `ValidationFailed("Пароль должен быть не длиннее 128 символов", code="password_too_long", details={"max_length": 128})`; `password.lower()` в `COMMON_PASSWORDS` → `ValidationFailed("Этот пароль слишком распространён — выберите другой", code="password_too_common")`.
- `common_passwords.txt`: не меньше 150 паролей длиной ≥ 6 — цифровые последовательности и повторы (`123456`…`1234567890`, `111111`, `00000000`), раскладки (`qwerty`, `qwerty123`, `qwertyuiop`, `asdfgh`, `zxcvbnm`, `1q2w3e4r`, `йцукен`, `йцукен123`, `фывапролдж`), слова (`password`, `password1`, `passw0rd`, `пароль`, `parol`, `iloveyou`, `admin123`, `welcome`, `english`, `teacher`), даты-шаблоны (`01012000` и т.п.). Источник — составлен вручную; можно заменить большим списком без изменения кода.
- `cli create-tutor`:
  - email нормализуется и проверяется **до** запроса пароля;
  - `sqlalchemy.exc.IntegrityError` (гонка второго репетитора) → «Репетитор уже создан», код 1;
  - `OSError` / `sqlalchemy.exc.OperationalError` / `sqlalchemy.exc.InterfaceError` → «Не удалось подключиться к базе данных: проверьте DATABASE_URL», код 1.

- [ ] **Step 1: Написать падающие тесты**

```python
@pytest.mark.parametrize("pw", ["12345678", "Qwerty123", "password", "йцукен123", "11111111"])
def test_common_passwords_rejected(pw):
    with pytest.raises(ValidationFailed) as e:
        validate_password(pw)
    assert e.value.code == "password_too_common"

def test_too_long_password_rejected():
    with pytest.raises(ValidationFailed) as e:
        validate_password("x" * 129)
    assert e.value.code == "password_too_long" and e.value.details == {"max_length": 128}

def test_child_min_length():
    validate_password("Ab3$xy", min_length=CHILD_PASSWORD_MIN_LENGTH)

def test_common_list_is_substantial():
    assert len(COMMON_PASSWORDS) >= 150 and all(len(p) >= 6 for p in COMMON_PASSWORDS)

# tests/auth/test_cli.py
def test_cli_invalid_email_fails_before_password_prompt(cli_env):
    r = CliRunner().invoke(cli, ["create-tutor", "--email", "not-an-email"])  # без input
    assert r.exit_code == 1 and "Некорректный email" in r.output and "Пароль" not in r.output

def test_cli_database_unreachable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/x")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_settings.cache_clear()
    r = CliRunner().invoke(cli, ["create-tutor", "--email", "t@x.ru", "--password-stdin"], input="Strong-pass-1\n")
    get_settings.cache_clear()
    assert r.exit_code == 1 and "Не удалось подключиться к базе данных" in r.output
```

Существующие тесты, где пароль `secret-pass`, оставить — его нет в списке; проверить, что `secret-pass`, `secret-pass` и `Пароль-123 !` в список не попали.

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/auth --no-cov`
Expected: FAIL — `password_too_common` не выбрасывается; CLI спрашивает пароль раньше проверки email.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-backend` и `just lint-backend`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(auth): common-password check, length limits, friendlier create-tutor errors"
```

---

### Task 3: Модели семей, детей, приглашений, сбросов и миграция 0002

**Files:**
- Create: `backend/app/families/__init__.py`, `backend/app/families/models.py`, `backend/migrations/versions/0002_families_auth_tokens.py`, `backend/tests/families/__init__.py`, `backend/tests/families/test_models.py`, `backend/tests/factories.py`
- Modify: `backend/app/auth/models.py`, `backend/migrations/env.py`, `backend/tests/test_migrations.py` (импорт новых моделей)

**Interfaces:**
- Produces (`app.families.models`):
  - `EnglishLevel(StrEnum)`: `A1`, `A2`, `B1`, `B2`, `C1` (значения — те же строки); PG enum `english_level`.
  - `Family(UUIDPrimaryKeyMixin, TimestampMixin, Base)`, таблица `families`: `name: str` (`String(200)`), `tutor_comment: str | None` (`Text`), `archived_at: datetime | None`.
  - `ParentProfile(TimestampMixin, Base)`, таблица `parent_profiles`: `user_id` PK, FK `users.id` `ondelete="CASCADE"`; `family_id` FK `families.id` `ondelete="CASCADE"`, `index=True`; `full_name: str` (`String(200)`); `phone: str` (`String(32)`); `consent_at: datetime`.
  - `Child(UUIDPrimaryKeyMixin, TimestampMixin, Base)`, таблица `children`: `family_id` FK `CASCADE`, `index=True`; `user_id: UUID | None` FK `users.id` `ondelete="SET NULL"`, `unique=True`; `full_name` (`String(200)`); `birth_year: int | None`; `english_level: EnglishLevel | None`; `default_meeting_url: str | None` (`String(500)`); `archived_at: datetime | None`. `CheckConstraint("birth_year BETWEEN 1990 AND 2100", name="birth_year_range")`.
  - Поля `birth_year`, `english_level`, `default_meeting_url` допускают NULL (репетитор может не знать их при создании; в спецификации 3.1 они без явного NULL — решение плана).
- Produces (`app.auth.models`):
  - `Invitation(UUIDPrimaryKeyMixin, TimestampMixin, Base)`, таблица `invitations`: `token_hash: str` (`String(64)`, unique), `family_id` FK `families.id` `CASCADE`, `prefill_full_name: str | None` (`String(200)`), `prefill_phone: str | None` (`String(32)`), `expires_at: datetime`, `used_at: datetime | None`, `revoked_at: datetime | None`, `created_by` FK `users.id`.
  - `PasswordReset(UUIDPrimaryKeyMixin, TimestampMixin, Base)`, таблица `password_resets`: `token_hash` (`String(64)`, unique), `user_id` FK `users.id` `CASCADE`, `expires_at`, `used_at: datetime | None`, `created_by` FK `users.id`.
- Produces (`tests/factories.py`, все функции делают `flush()`):
  - `TEST_PASSWORD = "Correct-Horse-7"`.
  - `async def make_tutor(session, *, email="tutor@example.com", password=TEST_PASSWORD) -> User`
  - `async def make_family(session, *, name="Ивановы", archived=False) -> Family`
  - `async def make_parent(session, family, *, email="parent@example.com", password=TEST_PASSWORD, full_name="Анна Иванова", phone="+79990000000", is_active=True) -> User`
  - `async def make_child(session, family, *, full_name="Маша", username: str | None = None, password=TEST_PASSWORD, archived=False) -> Child` (при `username` создаётся и `User(role=CHILD)`).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/families/test_models.py
async def test_child_user_is_unique(db_session): ...      # два Child с одним user_id → IntegrityError "uq_children_user_id"
async def test_birth_year_range(db_session): ...          # birth_year=1900 → IntegrityError "ck_children_birth_year_range"
async def test_deleting_family_cascades(db_session):
    fam = await make_family(db_session); child = await make_child(db_session, fam)
    await make_parent(db_session, fam)
    await db_session.delete(fam); await db_session.flush()
    assert await db_session.get(Child, child.id) is None
    assert (await db_session.scalar(select(func.count()).select_from(ParentProfile))) == 0
async def test_invitation_token_hash_unique(db_session): ...  # IntegrityError "uq_invitations_token_hash"
async def test_factories_build_consistent_family(db_session):
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")
    user = await db_session.get(User, child.user_id)
    assert user.role is UserRole.CHILD and user.username == "masha"
```

`tests/test_migrations.py` уже проверяет round-trip и пустой diff — новые модели должны импортироваться там и в `migrations/env.py`.

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/families tests/test_migrations.py --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.families'`.

- [ ] **Step 3: Реализовать модели и фабрики; сгенерировать миграцию `--rev-id 0002` (как в плане 1, временный PostgreSQL на 55432), вычитать: `downgrade` удаляет таблицы в обратном порядке и enum `english_level`**

- [ ] **Step 4: Проверить**

Run: `just test-backend` и `just lint-backend`
Expected: всё зелёное, `test_models_match_migrations` — пустой diff.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(families): families, parents, children, invitation and reset tables"
```

---

### Task 4: Хранилище сессий в Redis

**Files:**
- Create: `backend/app/auth/sessions.py`, `backend/app/auth/tokens.py` (пока только `sha256_hex`), `backend/tests/auth/test_sessions.py`
- Modify: `backend/app/core/redis.py`, `backend/app/core/config.py`, `.env.example`, `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `UserRole` (план 1), `create_redis`.
- Produces:
  - `Settings.session_cookie_secure: bool = True`, `Settings.public_base_url: str = "http://localhost:3000"` (валидатор убирает завершающий `/`); в `.env.example` — `SESSION_COOKIE_SECURE=true`, `PUBLIC_BASE_URL=http://localhost:3000` с комментариями.
  - `app.core.redis.get_redis(request: Request) -> Redis` и `RedisClient = Annotated[Redis, Depends(get_redis)]`.
  - `app.auth.sessions`:
    - `SESSION_COOKIE = "session"`; `SESSION_TTL: dict[UserRole, timedelta] = {TUTOR: 7 дней, PARENT: 30 дней, CHILD: 30 дней}`.
    - `@dataclass(frozen=True) SessionData`: `user_id: uuid.UUID`, `role: UserRole`, `created_at: datetime`.
    - `class SessionStore(redis: Redis)`:
      - `async def create(self, user_id: uuid.UUID, role: UserRole) -> str` — токен `secrets.token_urlsafe(32)`; `SET session:{sha256} <json> EX ttl`; `SADD user_sessions:{user_id} <sha256>` + `EXPIRE` на 30 дней.
      - `async def get(self, token: str) -> SessionData | None` — `GETEX … EX ttl` (плавающий срок); битый JSON → `None`.
      - `async def delete(self, token: str) -> None` — удаляет ключ и запись в индексе.
      - `async def delete_all_for_user(self, user_id: uuid.UUID) -> int` — удаляет все ключи из индекса и сам индекс, возвращает число удалённых сессий.
    - `get_session_store(redis: RedisClient) -> SessionStore`; `SessionStoreDep = Annotated[SessionStore, Depends(get_session_store)]`.
    - `set_session_cookie(response: Response, token: str, role: UserRole, settings: Settings) -> None` (`max_age` = TTL роли, `httponly=True`, `secure=settings.session_cookie_secure`, `samesite="lax"`, `path="/"`), `clear_session_cookie(response: Response, settings: Settings) -> None`.
  - `tests/conftest.py`: фикстура `redis` (session-scoped `redis.asyncio.Redis` к контейнеру, `decode_responses=True`); фикстура `app` перед созданием приложения делает `FLUSHDB` (rate limit и сессии не текут между тестами).

- [ ] **Step 1: Написать падающие тесты**

```python
async def test_create_and_get(redis):
    store = SessionStore(redis); uid = new_uuid7()
    token = await store.create(uid, UserRole.PARENT)
    data = await store.get(token)
    assert data and data.user_id == uid and data.role is UserRole.PARENT
    assert await redis.ttl(f"session:{sha256_hex(token)}") > 29 * 86400

async def test_token_not_stored_in_plain(redis):
    token = await SessionStore(redis).create(new_uuid7(), UserRole.CHILD)
    assert all(token not in k for k in await redis.keys("*"))

async def test_get_extends_ttl(redis):
    store = SessionStore(redis); token = await store.create(new_uuid7(), UserRole.TUTOR)
    key = f"session:{sha256_hex(token)}"
    await redis.expire(key, 10)
    await store.get(token)
    assert await redis.ttl(key) > 6 * 86400

async def test_unknown_and_corrupt_tokens(redis):
    store = SessionStore(redis)
    assert await store.get("nope") is None
    await redis.set(f"session:{sha256_hex('bad')}", "{not json")
    assert await store.get("bad") is None

async def test_delete_all_for_user(redis):
    store = SessionStore(redis); uid = new_uuid7()
    t1 = await store.create(uid, UserRole.PARENT); t2 = await store.create(uid, UserRole.PARENT)
    other = await store.create(new_uuid7(), UserRole.PARENT)
    assert await store.delete_all_for_user(uid) == 2
    assert await store.get(t1) is None and await store.get(t2) is None and await store.get(other)

def test_public_base_url_trailing_slash_stripped(): ...  # Settings(..., public_base_url="https://x.ru/") → "https://x.ru"
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/auth/test_sessions.py tests/core/test_config.py --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.sessions'`.

- [ ] **Step 3: Реализовать по Interfaces (`app/auth/tokens.py`: `sha256_hex(token: str) -> str`; Task 8 дополнит модуль)**

- [ ] **Step 4: Проверить**

Run: `just test-backend` и `just lint-backend`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend .env.example
git commit -m "feat(auth): redis session store with sliding expiry"
```

---

### Task 5: Rate limiter

**Files:**
- Create: `backend/app/core/rate_limit.py`, `backend/tests/core/test_rate_limit.py`
- Modify: `backend/app/core/errors.py`

**Interfaces:**
- Produces:
  - `app.core.rate_limit.RateLimit` (`@dataclass(frozen=True)`): `limit: int`, `window_seconds: int`.
  - `class RateLimiter(redis: Redis, prefix: str = "rl")` — фиксированное окно на ключ:
    - `async def retry_after(self, key: str, rule: RateLimit) -> int | None` — если счётчик `>= limit`, вернуть оставшийся TTL ключа в секундах (≥ 1), иначе `None`.
    - `async def hit(self, key: str, rule: RateLimit) -> None` — `INCR`; при первом инкременте `EXPIRE window_seconds` (через `pipeline` с `EXPIRE … NX`).
    - `async def reset(self, key: str) -> None`.
  - `app.core.errors.RateLimited(AppError)`: 429, `code = "rate_limited"`, `message = "Слишком много попыток. Попробуйте позже."`; конструктор `RateLimited(retry_after: int)` кладёт `details={"retry_after": retry_after}`; обработчик `AppError` добавляет заголовок `Retry-After: <retry_after>` для `RateLimited`.
  - `app.core.errors.NotAuthenticated(AppError)`: 401, `code = "not_authenticated"`, `message = "Требуется вход"`.

- [ ] **Step 1: Написать падающие тесты**

```python
RULE = RateLimit(limit=3, window_seconds=60)

async def test_allows_until_limit(redis):
    rl = RateLimiter(redis)
    for _ in range(2):
        await rl.hit("k", RULE)
    assert await rl.retry_after("k", RULE) is None
    await rl.hit("k", RULE)
    ra = await rl.retry_after("k", RULE)
    assert ra is not None and 1 <= ra <= 60

async def test_window_is_not_extended_by_hits(redis):
    rl = RateLimiter(redis); await rl.hit("k", RULE)
    await redis.expire("rl:k", 5)
    await rl.hit("k", RULE)
    assert await redis.ttl("rl:k") <= 5

async def test_reset_and_key_isolation(redis): ...  # reset("k") → None; hits on "a" не влияют на "b"

async def test_rate_limited_response_has_retry_after(tclient):  # тестовый маршрут raise RateLimited(42)
    r = await tclient.get("/api/_t/limited")
    assert r.status_code == 429 and r.headers["Retry-After"] == "42"
    assert r.json()["error"]["details"] == {"retry_after": 42}
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/core/test_rate_limit.py --no-cov`
Expected: FAIL — нет модуля.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-backend` и `just lint-backend`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(core): redis fixed-window rate limiter and 429 error"
```

---

### Task 6: CSRF и тестовый клиент

**Files:**
- Create: `backend/app/core/csrf.py`, `backend/tests/core/test_csrf.py`
- Modify: `backend/app/main.py`, `backend/tests/conftest.py`, `backend/tests/core/test_errors.py`, `backend/tests/core/test_request_id.py`, `backend/tests/core/test_db_session.py`, `backend/tests/core/test_health.py`, `backend/tests/core/test_ready.py`

**Interfaces:**
- Consumes: `error_body`, `Settings.session_cookie_secure`.
- Produces:
  - `app.core.csrf.CSRF_COOKIE = "csrf_token"`, `CSRF_HEADER = "X-CSRF-Token"`, `SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})`.
  - `class CsrfMiddleware(app: ASGIApp)` — чистый ASGI: для `http`-запросов с путём `/api/…` и методом вне `SAFE_METHODS` требует непустые cookie и заголовок, равные по `hmac.compare_digest`; иначе отвечает `403` с `error_body("csrf_failed", "Сессия страницы устарела. Обновите страницу и повторите.")`.
  - `app.core.csrf.router`: `GET /auth/csrf` (operation `get_csrf`) → `204`; если в запросе уже есть cookie вида `^[A-Za-z0-9_-]{43}$` — оставляет её, иначе ставит новую (`secrets.token_urlsafe(32)`; `httponly=False`, `secure=settings.session_cookie_secure`, `samesite="lax"`, `path="/"`, без `max_age` — живёт до закрытия браузера).
  - Порядок в `create_app`: `app.add_middleware(CsrfMiddleware)` **до** `app.add_middleware(RequestIdMiddleware)` (последний добавленный — внешний, request id остаётся самым внешним).
  - `tests/conftest.py`: `@asynccontextmanager async def open_client(app: FastAPI, *, asgi: ASGIApp | None = None, raise_app_exceptions: bool = True) -> AsyncIterator[AsyncClient]` — lifespan, `base_url="https://test"`, `GET /api/auth/csrf`, затем `client.headers["X-CSRF-Token"] = client.cookies["csrf_token"]`. Фикстура `client` и все самописные клиенты тестов плана 1 переходят на `open_client` (в `test_db_session.py` после открытия клиента `events.clear()`).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/core/test_csrf.py — тестовый маршрут POST /api/_t/echo → {"ok": true}
async def test_post_without_token_is_rejected(app):
    async with LifespanManager(app), AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        r = await c.post("/api/_t/echo")
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"

async def test_header_must_match_cookie(app): ...      # cookie получен, заголовок "x" → 403
async def test_post_with_token_passes(client): assert (await client.post("/api/_t/echo")).status_code == 200
async def test_get_does_not_need_token(app): ...       # GET /api/health без cookie → 200
async def test_csrf_cookie_is_reused(client):
    before = client.cookies["csrf_token"]
    r = await client.get("/api/auth/csrf")
    assert r.status_code == 204 and client.cookies["csrf_token"] == before
async def test_csrf_cookie_attributes(app):
    ... set_cookie = r.headers["set-cookie"].lower()
    assert "samesite=lax" in set_cookie and "secure" in set_cookie and "httponly" not in set_cookie
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/core/test_csrf.py --no-cov`
Expected: FAIL — `/api/auth/csrf` → 404, POST без токена проходит.

- [ ] **Step 3: Реализовать по Interfaces и перевести тесты плана 1 на `open_client`**

- [ ] **Step 4: Проверить весь backend (тесты плана 1 с POST — `test_errors`, `test_db_session` — должны остаться зелёными через `open_client`)**

Run: `just test-backend`, `just lint-backend`, `just gen-api`
Expected: всё зелёное; в клиенте появился `getCsrf`.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(core): double-submit CSRF protection"
```

---

### Task 7: Текущий пользователь, вход, выход, `/auth/me`

**Files:**
- Create: `backend/app/auth/deps.py`, `backend/app/auth/schemas.py`, `backend/app/auth/router.py`, `backend/app/families/service.py` (только функции чтения из Interfaces), `backend/tests/auth/test_login.py`
- Modify: `backend/app/auth/service.py`, `backend/app/main.py`

**Interfaces:**
- Consumes: `SessionStoreDep`, `set_session_cookie`/`clear_session_cookie`, `RateLimiter`, `RateLimit`, `RateLimited`, `NotAuthenticated`, `NotFound`, `DbSession`, `verify_password`, `password_needs_rehash`, `hash_password`, `normalize_email`.
- Produces:
  - `app.families.service`:
    - `async def get_parent_profile(session, user_id: uuid.UUID) -> ParentProfile | None`
    - `async def get_family(session, family_id: uuid.UUID) -> Family | None`
    - `async def list_active_children(session, family_id: uuid.UUID) -> list[Child]` (`archived_at IS NULL`, сортировка по `full_name`)
    - `async def get_child_by_user(session, user_id: uuid.UUID) -> Child | None`
  - `app.auth.schemas`:
    - `LoginRequest`: `login: str` (1–254), `password: str` (1–128).
    - `ChildSummary`: `id: UUID`, `full_name: str`; `FamilySummary`: `id: UUID`, `name: str`.
    - `MeResponse`: `id: UUID`, `role: UserRole`, `display_name: str`, `email: str | None`, `username: str | None`, `family: FamilySummary | None`, `children: list[ChildSummary]`. `display_name`: tutor — email; parent — `ParentProfile.full_name`; child — `Child.full_name`. `children`: parent — активные дети семьи; child — `[он сам]`; tutor — `[]`.
  - `app.auth.service`:
    - `DUMMY_PASSWORD_HASH` — хеш случайной строки, вычисленный при импорте.
    - `def normalize_login(login: str) -> str` — `strip().lower()` (email и username хранятся в нижнем регистре).
    - `async def authenticate(session, *, login: str, password: str) -> User | None` — ищет по `email` или `username`; если не найден — `verify_password(DUMMY_PASSWORD_HASH, password)` (одинаковое время ответа) и `None`; неактивный → `None`; при успехе обновляет `last_login_at` и при `password_needs_rehash` — хеш.
    - `async def build_me(session, user: User) -> MeResponse`.
  - `app.auth.deps`:
    - `async def get_current_user(request: Request, session: DbSession, store: SessionStoreDep) -> User` — нет cookie / сессии → `NotAuthenticated`; пользователь не найден, `is_active=False` или роль в сессии не совпадает с ролью в БД → `store.delete(token)` и `NotAuthenticated`.
    - `CurrentUser = Annotated[User, Depends(get_current_user)]`.
    - `def require_roles(*roles: UserRole) -> Callable[..., Awaitable[User]]` — зависимость: роль вне `roles` → `NotFound()`.
    - `TutorUser`, `ParentUser`, `FamilyMember` (`PARENT`, `CHILD`) — `Annotated[User, Depends(require_roles(...))]`.
  - `app.auth.router` (`APIRouter(prefix="/auth", tags=["auth"], responses=API_ERROR_RESPONSES)`):
    - `POST /auth/login` (operation `login`) → `200 MeResponse` + cookie. Правила лимита: `LOGIN_PAIR = RateLimit(5, 900)` по ключу `login:{normalize_login(login)}:{ip}`, `LOGIN_IP = RateLimit(30, 900)` по ключу `login-ip:{ip}`; `ip = request.client.host if request.client else "unknown"`. Сначала `retry_after` по обоим → `RateLimited(max)`; неудача → `hit` по обоим и `AppError` 401 `invalid_credentials` «Неверный логин или пароль»; успех → `reset` пары, удаление старой сессии из cookie запроса (ротация), новая сессия.
    - `POST /auth/logout` (operation `logout`) → `204`, удаляет сессию из cookie (если есть) и очищает cookie; без сессии тоже `204`.
    - `GET /auth/me` (operation `get_me`) → `MeResponse`.
  - IP за nginx/прокси в этом плане берётся из `request.client` — проброс `X-Forwarded-For` (`uvicorn --proxy-headers`) настраивается в плане 7.
  - `tests/factories.py`: `async def login(client: AsyncClient, login: str, password: str = TEST_PASSWORD) -> Response` — `POST /api/auth/login`, `assert 200`.

- [ ] **Step 1: Написать падающие тесты**

```python
async def test_login_parent_sets_cookie_and_returns_me(client, db_session):
    fam = await make_family(db_session); await make_parent(db_session, fam)
    await make_child(db_session, fam, full_name="Маша")
    r = await client.post("/api/auth/login", json={"login": " Parent@Example.com ", "password": TEST_PASSWORD})
    assert r.status_code == 200
    me = r.json()
    assert me["role"] == "parent" and me["display_name"] == "Анна Иванова"
    assert me["family"]["name"] == "Ивановы" and [c["full_name"] for c in me["children"]] == ["Маша"]
    cookie = r.headers["set-cookie"].lower()
    assert "session=" in cookie and "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert (await client.get("/api/auth/me")).json()["id"] == me["id"]

async def test_login_child_by_username(client, db_session): ...   # username="masha", login="MASHA" → role child, children == [self]
async def test_wrong_password_and_unknown_login_look_the_same(client, db_session):
    ... r1 = wrong password; r2 = unknown login
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json() and r1.json()["error"]["code"] == "invalid_credentials"
async def test_inactive_user_cannot_login(client, db_session): ...  # is_active=False → 401 invalid_credentials
async def test_me_requires_session(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"

async def test_sixth_attempt_is_rate_limited_even_with_correct_password(client, db_session):
    fam = await make_family(db_session); await make_parent(db_session, fam)
    for _ in range(5):
        assert (await client.post("/api/auth/login", json={"login": "parent@example.com", "password": "wrong-pass-1"})).status_code == 401
    r = await client.post("/api/auth/login", json={"login": "parent@example.com", "password": TEST_PASSWORD})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    await make_parent(db_session, fam, email="other@example.com")
    assert (await client.post("/api/auth/login", json={"login": "other@example.com", "password": TEST_PASSWORD})).status_code == 200

async def test_ip_limit_after_30_failures(client): ...   # 30 разных логинов неверно → 31-й любой → 429
async def test_success_resets_pair_counter(client, db_session): ...  # 4 неудачи, успех, ещё 4 неудачи → не 429
async def test_login_rotates_session(client, db_session):
    ... first = client.cookies["session"]; await login(...) again
    assert client.cookies["session"] != first
    # старый токен больше не работает
async def test_logout(client, db_session):
    ... await login(client, ...); r = await client.post("/api/auth/logout")
    assert r.status_code == 204 and (await client.get("/api/auth/me")).status_code == 401
async def test_logout_without_session_is_204(client): ...
async def test_deactivated_user_session_is_rejected(client, db_session):
    ... await login(...); user.is_active = False; await db_session.flush()
    assert (await client.get("/api/auth/me")).status_code == 401
async def test_password_field_length_limit(client): ...  # password "x"*129 → 422 validation_error
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/auth/test_login.py --no-cov`
Expected: FAIL — `/api/auth/login` → 404.

- [ ] **Step 3: Реализовать по Interfaces; подключить `auth.router` в `create_app` с префиксом `/api`**

- [ ] **Step 4: Проверить**

Run: `just test-backend`, `just lint-backend`, `just gen-api`
Expected: всё зелёное; хуки `useLogin`, `useLogout`, `useGetMe`.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(auth): login, logout, me with redis sessions and rate limiting"
```

---

### Task 8: Приглашения, сброс и смена пароля

**Files:**
- Modify: `backend/app/auth/tokens.py`, `backend/app/auth/service.py`, `backend/app/auth/schemas.py`, `backend/app/auth/router.py`
- Create: `backend/tests/auth/test_invitations.py`, `backend/tests/auth/test_password_resets.py`, `backend/tests/auth/test_change_password.py`

**Interfaces:**
- Consumes: модели Task 3, `SessionStore`, `validate_password`, `normalize_email`, `Settings.public_base_url`.
- Produces:
  - `app.auth.tokens`: `sha256_hex(token: str) -> str` (из Task 4), `new_token() -> tuple[str, str]` (токен, его хеш), `INVITATION_TTL = timedelta(days=7)`, `RESET_TTL = timedelta(hours=24)`.
  - `app.auth.schemas`:
    - `InvitationInfo`: `family_name: str`, `expires_at: datetime`, `prefill_full_name: str | None`, `prefill_phone: str | None`.
    - `AcceptInvitationRequest`: `email: str` (≤ 254), `password: str` (≤ 128), `full_name: str` (1–200, `strip`), `phone: str` (шаблон `^\+?[0-9\s()-]{6,32}$`), `consent: Literal[True]`.
    - `PasswordResetInfo`: `expires_at: datetime`, `login: str` (email или username — чтобы человек видел, для какого аккаунта меняет пароль).
    - `ResetPasswordRequest`: `password: str` (≤ 128). `ChangePasswordRequest`: `current_password: str` (≤ 128), `new_password: str` (≤ 128).
    - `LinkResponse`: `url: str`, `expires_at: datetime` (для Task 9).
  - `app.auth.service`:
    - `async def create_invitation(session, *, family: Family, created_by: User, prefill_full_name: str | None, prefill_phone: str | None) -> tuple[str, Invitation]` — выставляет `revoked_at=now` всем неиспользованным и неотозванным приглашениям семьи, создаёт новое.
    - `async def get_valid_invitation(session, token: str) -> Invitation` — не найдено / `used_at` / `revoked_at` / `expires_at <= now` / семья в архиве → `NotFound("Ссылка-приглашение недействительна или устарела", code="invitation_invalid")`.
    - `async def accept_invitation(session, *, token: str, data: AcceptInvitationRequest) -> User` — блокирует строку приглашения `SELECT … FOR UPDATE`, повторно проверяет; email нормализуется; занят → `Conflict("Email уже используется", code="email_taken")`; `validate_password`; создаёт `User(role=PARENT)` и `ParentProfile(consent_at=now)`; `used_at=now`.
    - `async def create_password_reset(session, *, user: User, created_by: User) -> tuple[str, PasswordReset]` — гасит (`used_at=now`) прежние неиспользованные сбросы этого пользователя.
    - `async def get_valid_password_reset(session, token: str) -> PasswordReset` — иначе `NotFound("Ссылка для смены пароля недействительна или устарела", code="reset_invalid")`.
    - `async def reset_password(session, *, token: str, password: str, sessions: SessionStore) -> User` — `FOR UPDATE`; минимальная длина: `CHILD_PASSWORD_MIN_LENGTH` для ребёнка, иначе `PASSWORD_MIN_LENGTH`; `used_at=now`; `sessions.delete_all_for_user`.
    - `async def change_password(session, *, user: User, current_password: str, new_password: str, sessions: SessionStore) -> None` — неверный текущий → `ValidationFailed("Текущий пароль указан неверно", code="invalid_current_password", details={"field": "current_password"})`; удаляет все сессии пользователя.
    - `def build_link(settings: Settings, path: str, token: str) -> str` → `f"{settings.public_base_url}/{path}/{token}"` (`path` — `invite` или `reset`).
  - `app.auth.router`:
    - `GET /auth/invitations/{token}` (operation `get_invitation`) → `InvitationInfo`.
    - `POST /auth/invitations/{token}/accept` (operation `accept_invitation`) → `201 MeResponse` + cookie сессии.
    - `GET /auth/password-resets/{token}` (operation `get_password_reset`) → `PasswordResetInfo`.
    - `POST /auth/password-resets/{token}` (operation `reset_password`) → `204` (пользователь затем входит сам).
    - `POST /auth/password` (operation `change_password`, `CurrentUser`) → `204` + новая сессия в cookie (текущее устройство остаётся в системе, остальные выходят).

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/auth/test_invitations.py — приглашения создаются сервисом напрямую в тесте
async def test_invitation_info(client, db_session): ...  # family_name, prefill_* и expires_at ≈ now+7d
async def test_accept_creates_parent_and_logs_in(client, db_session):
    tutor = await make_tutor(db_session); fam = await make_family(db_session)
    token, _ = await create_invitation(db_session, family=fam, created_by=tutor, prefill_full_name="Анна", prefill_phone=None)
    r = await client.post(f"/api/auth/invitations/{token}/accept", json={
        "email": " Anna@Mail.RU ", "password": TEST_PASSWORD, "full_name": "Анна Иванова",
        "phone": "+7 (999) 000-00-00", "consent": True})
    assert r.status_code == 201 and r.json()["role"] == "parent" and r.json()["email"] == "anna@mail.ru"
    profile = await db_session.get(ParentProfile, uuid.UUID(r.json()["id"]))
    assert profile.consent_at is not None and profile.family_id == fam.id
    assert (await client.get("/api/auth/me")).status_code == 200

async def test_accept_twice_fails(client, db_session): ...           # второй accept → 404 invitation_invalid, пользователей-родителей 1
async def test_expired_invitation(client, db_session): ...           # expires_at в прошлом → GET и accept → 404 invitation_invalid
async def test_new_invitation_revokes_previous(client, db_session): ...  # старый токен → 404
async def test_archived_family_invitation_invalid(client, db_session): ...
async def test_consent_required(client, db_session): ...             # consent false → 422 validation_error, поле consent
async def test_email_taken(client, db_session): ...                  # → 409 email_taken, приглашение не погашено
async def test_common_password_rejected_on_accept(client, db_session): ...  # "12345678" → 422 password_too_common

# tests/auth/test_password_resets.py
async def test_reset_flow_kills_sessions(client, db_session):
    tutor = await make_tutor(db_session); fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    await login(client, "parent@example.com")
    token, _ = await create_password_reset(db_session, user=parent, created_by=tutor)
    info = (await client.get(f"/api/auth/password-resets/{token}")).json()
    assert info["login"] == "parent@example.com"
    assert (await client.post(f"/api/auth/password-resets/{token}", json={"password": "New-Strong-9"})).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401
    await login(client, "parent@example.com", "New-Strong-9")

async def test_reset_link_single_use(client, db_session): ...        # второй POST → 404 reset_invalid
async def test_child_reset_allows_six_chars(client, db_session): ... # ребёнок, "Ab3$xy" → 204
async def test_new_reset_invalidates_previous(client, db_session): ...

# tests/auth/test_change_password.py
async def test_change_password_keeps_current_device_and_logs_out_others(client, db_session, app):
    ... await login(client, ...); async with open_client(app) as other: await login(other, ...)
    r = await client.post("/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "New-Strong-9"})
    assert r.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 200
    assert (await other.get("/api/auth/me")).status_code == 401
async def test_wrong_current_password(client, db_session): ...       # 422 invalid_current_password, details.field == "current_password"
async def test_change_password_requires_login(client): ...           # 401
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/auth --no-cov`
Expected: FAIL — `ImportError: cannot import name 'create_invitation'`.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-backend`, `just lint-backend`, `just gen-api`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(auth): parent invitations, password reset links, password change"
```

---

### Task 9: Админ-API семей, детей и пользователей

**Files:**
- Create: `backend/app/families/schemas.py`, `backend/app/families/admin_router.py`, `backend/tests/families/test_admin_families.py`, `backend/tests/families/test_admin_children.py`, `backend/tests/families/test_admin_users.py`
- Modify: `backend/app/families/service.py`, `backend/app/main.py`

**Interfaces:**
- Consumes: `TutorUser`, `DbSession`, `SessionStoreDep`, `create_invitation`, `create_password_reset`, `build_link`, `LinkResponse`, `normalize_username`, `validate_password`, `CHILD_PASSWORD_MIN_LENGTH`, `hash_password`.
- Produces (`app.families.schemas`):
  - `FamilyCreate`: `name: str` (1–200, strip), `tutor_comment: str | None` (≤ 2000).
  - `FamilyUpdate`: `name`, `tutor_comment`, `archived: bool | None` — все необязательные.
  - `InvitationCreate`: `prefill_full_name: str | None` (≤ 200), `prefill_phone: str | None` (≤ 32); тело запроса необязательно.
  - `ChildCreate`: `full_name: str` (1–200), `birth_year: int | None` (1990…текущий год), `english_level: EnglishLevel | None`, `default_meeting_url: HttpUrl | None` (≤ 500; хранится строкой).
  - `ChildUpdate`: те же поля необязательные + `archived: bool | None`.
  - `ChildAccountSet`: `username: str`, `password: str` (≤ 128).
  - `UserStatusUpdate`: `is_active: bool`.
  - `ChildAccount`: `user_id`, `username`, `is_active`. `ChildDetail`: `id`, `full_name`, `birth_year`, `english_level`, `default_meeting_url`, `archived_at`, `account: ChildAccount | None`.
  - `ParentDetail`: `user_id`, `full_name`, `phone`, `email`, `is_active`, `last_login_at`.
  - `PendingInvitation`: `created_at`, `expires_at`.
  - `FamilyDetail`: `id`, `name`, `tutor_comment`, `archived_at`, `created_at`, `parents: list[ParentDetail]`, `children: list[ChildDetail]` (включая архивных, сначала активные), `pending_invitation: PendingInvitation | None`.
  - `FamilyListItem`: `id`, `name`, `archived_at`, `parent_names: list[str]`, `children: list[ChildSummary]` (только активные).
- Produces (`app.families.service`):
  - `async def list_families(session, *, q: str | None, archived: bool) -> list[FamilyListItem]` — `q` ищет `ILIKE` (с экранированием `%`, `_`, `\`) по имени семьи, ФИО родителя и имени ребёнка; `archived=False` → `archived_at IS NULL`, `True` → `IS NOT NULL`; сортировка по `name`.
  - `async def create_family(session, data: FamilyCreate) -> Family`.
  - `async def get_family_detail(session, family_id) -> FamilyDetail` — нет → `NotFound`.
  - `async def update_family(session, family_id, data: FamilyUpdate, *, sessions: SessionStore) -> FamilyDetail` — `archived=True`: `archived_at=now`, все пользователи семьи (родители и дети) `is_active=False` + `delete_all_for_user`; `archived=False`: `archived_at=None`, снова активны родители семьи и учётки её неархивных детей.
  - `async def add_child(session, family_id, data: ChildCreate) -> ChildDetail` — семья в архиве → `Conflict("Семья в архиве", code="family_archived")`.
  - `async def update_child(session, child_id, data: ChildUpdate, *, sessions) -> ChildDetail` — `archived=True` деактивирует учётку ребёнка и удаляет её сессии; `archived=False` при архивной семье → `Conflict(code="family_archived")`.
  - `async def set_child_account(session, child: Child, data: ChildAccountSet, *, sessions) -> Child` — `normalize_username`; занят другим пользователем → `Conflict("Логин уже занят", code="username_taken")`; `validate_password(min_length=CHILD_PASSWORD_MIN_LENGTH)`; учётки нет — создаёт `User(role=CHILD)`; есть — меняет логин и пароль, удаляет её сессии. Архивный ребёнок → `Conflict("Ученик в архиве", code="child_archived")`.
  - `async def get_family_user(session, user_id) -> User` — только `parent`/`child`, иначе `NotFound` (репетитор недоступен через эти эндпоинты).
  - `async def set_user_active(session, user: User, is_active: bool, *, sessions) -> None` — при `False` удаляет все сессии.
- Produces (`app.families.admin_router`, `APIRouter(prefix="/admin", tags=["admin"], responses=API_ERROR_RESPONSES)`, все — `TutorUser`):

| Метод и путь | operation | Ответ |
|---|---|---|
| `GET /admin/families?q=&archived=false` | `list_families` | `list[FamilyListItem]` |
| `POST /admin/families` | `create_family` | `201 FamilyDetail` |
| `GET /admin/families/{family_id}` | `get_family` | `FamilyDetail` |
| `PATCH /admin/families/{family_id}` | `update_family` | `FamilyDetail` |
| `POST /admin/families/{family_id}/invitations` | `create_family_invitation` | `201 LinkResponse` (`url = build_link(settings, "invite", token)`) |
| `POST /admin/families/{family_id}/children` | `add_child` | `201 ChildDetail` |
| `PATCH /admin/children/{child_id}` | `update_child` | `ChildDetail` |
| `POST /admin/children/{child_id}/account` | `set_child_account_admin` | `ChildDetail` |
| `POST /admin/users/{user_id}/reset-link` | `create_reset_link` | `201 LinkResponse` (`"reset"`) |
| `PATCH /admin/users/{user_id}` | `update_user_status` | `204` |

- [ ] **Step 1: Написать падающие тесты**

```python
# фикстура tutor_client: make_tutor + login(client, "tutor@example.com")
async def test_parent_cannot_reach_admin(client, db_session):
    fam = await make_family(db_session); await make_parent(db_session, fam); await login(client, "parent@example.com")
    for method, url in [("GET", "/api/admin/families"), ("POST", "/api/admin/families"), ("GET", f"/api/admin/families/{fam.id}")]:
        r = await client.request(method, url, json={"name": "x"})
        assert r.status_code == 404, url

async def test_anonymous_admin_is_401(client): ...
async def test_create_and_get_family(tutor_client): ...           # 201, name, пустые parents/children
async def test_search_by_parent_and_child_name(tutor_client, db_session): ...  # q="анна" находит, q="маш" находит, q="%" не находит всё подряд
async def test_invitation_link(tutor_client, db_session):
    ... r = await tutor_client.post(f"/api/admin/families/{fam.id}/invitations", json={"prefill_full_name": "Анна"})
    assert r.status_code == 201 and r.json()["url"].startswith("http://localhost:3000/invite/")
    token = r.json()["url"].rsplit("/", 1)[1]
    assert (await tutor_client.get(f"/api/auth/invitations/{token}")).json()["prefill_full_name"] == "Анна"
    detail = (await tutor_client.get(f"/api/admin/families/{fam.id}")).json()
    assert detail["pending_invitation"] is not None
async def test_archive_family_logs_out_members(app, tutor_client, db_session):
    ... parent logged in via open_client(app); PATCH archived=true
    assert (await parent_client.get("/api/auth/me")).status_code == 401
    # повторный вход тоже невозможен (is_active=False), разархивация возвращает доступ
async def test_add_child_to_archived_family_conflict(tutor_client, db_session): ...  # 409 family_archived

# tests/families/test_admin_children.py
async def test_add_and_update_child(tutor_client, db_session): ...       # english_level "B1", url, birth_year
async def test_child_validation(tutor_client, db_session): ...           # birth_year 1980 → 422; url "ftp://x" → 422
async def test_set_child_account_then_child_logs_in(app, tutor_client, db_session):
    ... r = POST /api/admin/children/{id}/account {"username": " Masha.K ", "password": "Ab3$xy"}
    assert r.json()["account"]["username"] == "masha.k"
    async with open_client(app) as kid: await login(kid, "masha.k", "Ab3$xy")
async def test_username_taken(tutor_client, db_session): ...             # 409 username_taken
async def test_cyrillic_username_rejected(tutor_client, db_session): ... # 422 invalid_username
async def test_changing_child_account_logs_child_out(app, tutor_client, db_session): ...
async def test_archive_child_deactivates_account(app, tutor_client, db_session): ...

# tests/families/test_admin_users.py
async def test_reset_link_for_parent(tutor_client, db_session): ...      # url .../reset/<token>, GET info → login
async def test_reset_link_for_tutor_is_404(tutor_client, db_session): ...
async def test_deactivate_user_kills_sessions(app, tutor_client, db_session): ...
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/families --no-cov`
Expected: FAIL — `/api/admin/families` → 404 для репетитора.

- [ ] **Step 3: Реализовать по Interfaces; подключить роутер в `create_app`**

- [ ] **Step 4: Проверить**

Run: `just test-backend`, `just lint-backend`, `just gen-api`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(families): tutor admin API for families, children, accounts, links"
```

---

### Task 10: `family_scope` и API кабинета

**Files:**
- Create: `backend/app/families/scope.py`, `backend/app/families/cabinet_router.py`, `backend/tests/families/test_cabinet.py`
- Modify: `backend/app/families/schemas.py`, `backend/app/main.py`

**Interfaces:**
- Consumes: `FamilyMember`, `ParentUser`, `set_child_account`, `get_parent_profile`, `get_child_by_user`, `list_active_children`.
- Produces:
  - `app.families.scope.FamilyScope` (`@dataclass(frozen=True)`): `family_id: uuid.UUID`, `child_ids: frozenset[uuid.UUID]`.
  - `async def get_family_scope(user: FamilyMember, session: DbSession) -> FamilyScope` — parent: семья профиля, `child_ids` — активные дети; child: семья ребёнка, `child_ids = {свой id}`; ребёнок в архиве / профиль не найден → `NotAuthenticated`. `FamilyScopeDep = Annotated[FamilyScope, Depends(get_family_scope)]`. План 5 фильтрует занятия только через `scope.child_ids`.
  - `app.families.schemas.CabinetChild`: `id`, `full_name`, `birth_year`, `english_level`, `username: str | None`.
  - `app.families.cabinet_router` (`prefix="/me"`, `tags=["cabinet"]`):
    - `GET /me/children` (operation `list_my_children`, `FamilyScopeDep`) → `list[CabinetChild]` — дети из `scope.child_ids`.
    - `POST /me/children/{child_id}/account` (operation `set_my_child_account`, `ParentUser` + `FamilyScopeDep`) → `CabinetChild`; `child_id` вне `scope.child_ids` → `NotFound`.

- [ ] **Step 1: Написать падающие тесты**

```python
async def test_parent_sees_only_active_children_of_own_family(client, db_session):
    a = await make_family(db_session, name="A"); b = await make_family(db_session, name="B")
    await make_parent(db_session, a); await make_child(db_session, a, full_name="Маша")
    await make_child(db_session, a, full_name="Петя", archived=True); await make_child(db_session, b, full_name="Чужой")
    await login(client, "parent@example.com")
    assert [c["full_name"] for c in (await client.get("/api/me/children")).json()] == ["Маша"]

async def test_child_sees_only_self(client, db_session): ...
async def test_parent_sets_child_account(client, db_session): ...           # username в ответе, ребёнок затем входит
async def test_parent_cannot_touch_other_family_child(client, db_session):
    ... r = await client.post(f"/api/me/children/{foreign.id}/account", json={"username": "hack", "password": "Ab3$xy"})
    assert r.status_code == 404
async def test_child_cannot_set_accounts(client, db_session): ...           # 404
async def test_tutor_has_no_cabinet(client, db_session): ...                # tutor GET /api/me/children → 404
async def test_scope_child_ids(db_session): ...                             # прямой вызов get_family_scope для parent и child
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/families/test_cabinet.py --no-cov`
Expected: FAIL — `/api/me/children` → 404 для родителя.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-backend` (покрытие ≥ 85%), `just lint-backend`, `just gen-api`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(families): family scope and cabinet children API"
```

---

### Task 11: Frontend — API-слой: CSRF, политика повторов, 401

**Files:**
- Create: `frontend/src/lib/query-client.ts`, `frontend/src/lib/query-client.test.ts`, `frontend/src/lib/auth.ts`, `frontend/src/lib/auth.test.ts`
- Modify: `frontend/src/lib/api-fetch.ts`, `frontend/src/lib/api-fetch.test.ts`, `frontend/src/app/providers.tsx`

**Interfaces:**
- Consumes: сгенерированные `getCsrf` и `ApiError`.
- Produces:
  - `api-fetch.ts`:
    - для методов вне `GET/HEAD/OPTIONS`: читает cookie `csrf_token` из `document.cookie`; нет — сначала `GET /api/auth/csrf` (тем же `fetch`, `credentials: "same-origin"`); ставит заголовок `X-CSRF-Token`;
    - ответ 403 с `code === "csrf_failed"` → один раз запрашивает новый токен и повторяет запрос;
    - `AbortError` (`init.signal?.aborted` или `error.name === "AbortError"`) пробрасывается как есть, не превращается в `network_error`;
    - `export type ErrorType<E> = ApiError;` и `export type BodyType<B> = B;` — orval подхватывает их, и `TError` хуков становится `ApiError`.
  - `query-client.ts`:
    - `shouldRetry(failureCount: number, error: unknown): boolean` — `false` для `ApiError` со статусом 400–499; иначе `failureCount < 1`.
    - `makeQueryClient(onUnauthenticated: () => void): QueryClient` — `staleTime: 30_000`, `retry: shouldRetry`, мутации без повторов; `QueryCache`/`MutationCache` `onError`: `ApiError` 401 и у запроса нет `meta.skipAuthRedirect` → `onUnauthenticated()`.
  - `providers.tsx`: `onUnauthenticated` → `window.location.assign("/login?next=" + encodeURIComponent(location.pathname + location.search))`, если текущий путь не `/login`, не `/invite/*`, не `/reset/*`.
  - `auth.ts`:
    - `homeFor(role: UserRole): "/admin" | "/cabinet"`.
    - `safeNext(next: string | null): string | null` — только путь, начинающийся с одиночного `/`, без `//`, `/\`, схемы и управляющих символов; иначе `null`.
  - После правки: `just gen-api` (типы ошибок хуков меняются на `ApiError`).

- [ ] **Step 1: Написать падающие тесты**

```ts
// api-fetch.test.ts — добавить
test("POST добавляет CSRF-заголовок из cookie", async () => {
  document.cookie = "csrf_token=tok123";
  const f = stubFetch(new Response("{}", { status: 200 }));
  await apiFetch("/api/x", { method: "POST" });
  expect(new Headers((f.mock.calls[0][1] as RequestInit).headers).get("X-CSRF-Token")).toBe("tok123");
});
test("без cookie сначала получает токен", async () => { /* первый вызов fetch — /api/auth/csrf; в ответе ставим document.cookie */ });
test("csrf_failed → обновить токен и повторить один раз", async () => { /* 403 csrf_failed, затем /api/auth/csrf, затем 200 → resolves; fetch вызван 3 раза */ });
test("отмена запроса не превращается в network_error", async () => {
  const ctrl = new AbortController(); ctrl.abort();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")));
  await expect(apiFetch("/api/x", { signal: ctrl.signal })).rejects.toMatchObject({ name: "AbortError" });
});

// query-client.test.ts
test.each([[400, false], [401, false], [404, false], [429, false], [500, true], [0, true]])(
  "shouldRetry для статуса %i → %s", (status, expected) => {
    expect(shouldRetry(0, new ApiError(status, "x", "x"))).toBe(expected);
  });
test("второй повтор не делается", () => expect(shouldRetry(1, new ApiError(500, "x", "x"))).toBe(false));
test("401 вызывает onUnauthenticated, кроме skipAuthRedirect", async () => { /* QueryClient.fetchQuery с queryFn, бросающей ApiError(401) */ });

// auth.test.ts
test.each([
  ["/cabinet", "/cabinet"], ["/admin/families?x=1", "/admin/families?x=1"],
  ["//evil.com", null], ["https://evil.com", null], ["/\\evil.com", null], ["evil", null], [null, null], ["/a\nb", null],
])("safeNext(%s) → %s", (input, expected) => expect(safeNext(input)).toBe(expected));
test("homeFor", () => { expect(homeFor("tutor")).toBe("/admin"); expect(homeFor("parent")).toBe("/cabinet"); expect(homeFor("child")).toBe("/cabinet"); });
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-frontend`
Expected: FAIL — нет заголовка CSRF, нет модулей `query-client`, `auth`.

- [ ] **Step 3: Реализовать по Interfaces; `just gen-api`**

- [ ] **Step 4: Проверить**

Run: `just lint-frontend`, `just test-frontend`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): csrf-aware fetch, retry policy, 401 redirect"
```

---

### Task 12: Frontend — UI-кит и вспомогательные компоненты

**Files:**
- Create: `frontend/src/components/ui/*` (shadcn), `frontend/src/components/password-field.tsx`, `frontend/src/components/copy-link-card.tsx`, `frontend/src/components/copy-link-card.test.tsx`, `frontend/src/lib/form-errors.ts`, `frontend/src/lib/form-errors.test.ts`
- Modify: `frontend/package.json`, `frontend/src/app/layout.tsx` (`<Toaster />`)

**Interfaces:**
- Produces:
  - `pnpm --dir frontend add react-hook-form @hookform/resolvers`; `pnpm --dir frontend dlx shadcn@latest add input label card alert badge dialog table select checkbox textarea sonner -c <абсолютный путь frontend>`.
  - `form-errors.ts`:
    - `applyApiErrors<T extends FieldValues>(error: unknown, setError: UseFormSetError<T>, fields: readonly Path<T>[]): string | null` — `ApiError` с `details.fields` (422 Pydantic): для каждого элемента берёт последний сегмент `loc`; если он в `fields` — `setError(name, {message})`. `ApiError` с `details.field` в `fields` — ошибка на это поле с `error.message`. Возвращает текст для общей ошибки формы (если что-то не легло на поле) или `null`.
    - `errorMessage(error: unknown): string` — `ApiError.message`, иначе «Что-то пошло не так. Попробуйте ещё раз.».
  - `PasswordField` — `Input type=password` с кнопкой «Показать/Скрыть» (`aria-label`), пробрасывает `ref` и props react-hook-form.
  - `CopyLinkCard({ url, expiresAt, title }: { url: string; expiresAt: string; title: string })` — поле только для чтения с URL, кнопка «Скопировать» (`navigator.clipboard.writeText`, затем текст «Скопировано»), строка «Действует до <дата в Europe/Moscow, формат `dd.MM.yyyy HH:mm`>» через `Intl.DateTimeFormat("ru-RU", …)`.

- [ ] **Step 1: Написать падающие тесты**

```ts
test("ошибки Pydantic ложатся на поля", () => {
  const setError = vi.fn();
  const err = new ApiError(422, "validation_error", "Ошибка валидации",
    { fields: [{ loc: ["body", "email"], message: "bad", type: "value_error" }] });
  expect(applyApiErrors(err, setError, ["email", "password"])).toBeNull();
  expect(setError).toHaveBeenCalledWith("email", { message: "bad" });
});
test("доменная ошибка с details.field ложится на поле", () => { /* invalid_current_password → current_password */ });
test("неизвестная ошибка → общий текст", () => { /* ApiError 409 email_taken без field → "Email уже используется" */ });

test("CopyLinkCard копирует ссылку", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
  render(<CopyLinkCard title="Приглашение" url="http://x/invite/t" expiresAt="2026-10-18T09:00:00Z" />);
  await userEvent.click(screen.getByRole("button", { name: "Скопировать" }));
  expect(writeText).toHaveBeenCalledWith("http://x/invite/t");
  expect(await screen.findByText("Скопировано")).toBeInTheDocument();
  expect(screen.getByText(/18\.10\.2026 12:00/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-frontend`
Expected: FAIL — модулей нет.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just lint-frontend`, `just test-frontend`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): ui kit, form error mapping, copy-link card"
```

---

### Task 13: Frontend — `/login` и защита маршрутов

**Files:**
- Create: `frontend/src/proxy.ts`, `frontend/src/proxy.test.ts`, `frontend/src/app/login/page.tsx`, `frontend/src/app/login/login-form.tsx`, `frontend/src/app/login/login-form.test.tsx`

**Interfaces:**
- Consumes: `useLogin`, `useGetMe`, `safeNext`, `homeFor`, `applyApiErrors`, `PasswordField`.
- Produces:
  - `src/proxy.ts`: `export function proxy(request: NextRequest)` — для путей `/cabinet/:path*`, `/admin/:path*` без cookie `session` → `NextResponse.redirect(new URL("/login?next=" + encodeURIComponent(pathname + search), request.url))`; иначе `NextResponse.next()`. `export const config = { matcher: ["/cabinet/:path*", "/admin/:path*"] }`.
  - `/login` (`page.tsx` — серверный, `metadata.title = "Вход"`, `robots: { index: false }`; рендерит `<Suspense><LoginForm /></Suspense>`).
  - `LoginForm` (клиентский): поля «Email или логин» и «Пароль» (zod: оба обязательны, пароль ≤ 128); отправка через `useLogin`; успех → `router.replace(safeNext(searchParams.get("next")) ?? homeFor(me.role))`; ошибки: `invalid_credentials` → общий текст «Неверный логин или пароль»; `rate_limited` → «Слишком много попыток. Попробуйте через N мин.» (N = `ceil(retry_after / 60)`); прочее — `errorMessage`. Кнопка блокируется на время запроса. Если `useGetMe` (с `meta: { skipAuthRedirect: true }`, `retry: false`) уже вернул пользователя — сразу редирект на `homeFor(role)`.

- [ ] **Step 1: Написать падающие тесты**

```ts
// proxy.test.ts
test("без cookie → редирект на /login с next", () => {
  const res = proxy(new NextRequest("http://localhost:3000/admin/families?x=1"));
  expect(res.headers.get("location")).toBe("http://localhost:3000/login?next=%2Fadmin%2Ffamilies%3Fx%3D1");
});
test("с cookie session → пропускает", () => {
  const req = new NextRequest("http://localhost:3000/cabinet", { headers: { cookie: "session=abc" } });
  expect(proxy(req).headers.get("location")).toBeNull();
});

// login-form.test.tsx — next/navigation замокан (useRouter → { replace }), fetch замокан
test("успешный вход ведёт на next, если он безопасен", async () => { /* ?next=/cabinet/settings → replace("/cabinet/settings") */ });
test("опасный next игнорируется", async () => { /* ?next=//evil.com, роль tutor → replace("/admin") */ });
test("неверный пароль показывает общую ошибку", async () => { /* 401 invalid_credentials → "Неверный логин или пароль" */ });
test("лимит попыток показывает минуты", async () => { /* 429 retry_after 600 → "через 10 мин" */ });
test("пустые поля не отправляются", async () => { /* fetch не вызван, видны сообщения валидации */ });
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-frontend`
Expected: FAIL — модулей нет.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just lint-frontend`, `just test-frontend`, `pnpm --dir frontend build`
Expected: всё зелёное; сборка без ошибок о `useSearchParams` вне `Suspense`.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): login page and route guard proxy"
```

---

### Task 14: Frontend — `/invite/[token]` и `/reset/[token]`

**Files:**
- Create: `frontend/src/app/invite/[token]/page.tsx`, `frontend/src/app/invite/[token]/accept-invitation.tsx`, `frontend/src/app/invite/[token]/accept-invitation.test.tsx`, `frontend/src/app/reset/[token]/page.tsx`, `frontend/src/app/reset/[token]/reset-password.tsx`, `frontend/src/app/reset/[token]/reset-password.test.tsx`

**Interfaces:**
- Consumes: `useGetInvitation`, `useAcceptInvitation`, `useGetPasswordReset`, `useResetPassword`, `applyApiErrors`, `PasswordField`.
- Produces:
  - Обе `page.tsx` — серверные (`robots: { index: false }`), рендерят клиентский компонент в `<Suspense>`; токен клиент берёт из `useParams<{ token: string }>()`.
  - `AcceptInvitation`: загрузка → `useGetInvitation(token, { query: { meta: { skipAuthRedirect: true }, retry: false } })`; `invitation_invalid` → карточка «Ссылка недействительна или устарела. Попросите репетитора прислать новую.»; иначе заголовок «Приглашение в семью «{family_name}»», поля ФИО и телефон (предзаполнены), email, пароль, повтор пароля (совпадение — zod `refine`), чекбокс «Согласен на обработку персональных данных» со ссылкой на `/privacy` (обязателен); успех → `router.replace("/cabinet")`. Ошибки API раскладываются через `applyApiErrors` по полям `email`, `password`, `full_name`, `phone`, `consent`.
  - `ResetPassword`: `reset_invalid` → «Ссылка для смены пароля недействительна или устарела. Попросите репетитора прислать новую.»; иначе «Новый пароль для {login}», пароль + повтор; успех → сообщение «Пароль изменён» и ссылка «Войти» на `/login`.
  - Страница `/privacy` в этом плане не создаётся (план 3); ссылка открывается в новой вкладке.

- [ ] **Step 1: Написать падающие тесты**

```ts
test("недействительное приглашение показывает понятный текст", async () => { /* GET → 404 invitation_invalid */ });
test("предзаполняет ФИО и телефон", async () => { /* значения инпутов */ });
test("без согласия форма не отправляется", async () => { /* accept не вызван, сообщение у чекбокса */ });
test("пароли должны совпадать", async () => {});
test("email_taken показывается у поля email", async () => { /* 409 email_taken, details {} → applyApiErrors: общая ошибка формы */ });
test("успех ведёт в кабинет", async () => { /* replace("/cabinet") */ });
test("сброс: успех показывает «Пароль изменён» и ссылку на вход", async () => {});
test("сброс: недействительная ссылка", async () => {});
```

Для `email_taken` у сервиса нет `details.field` — сообщение показывается как общая ошибка формы над кнопкой (поведение `applyApiErrors`).

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-frontend`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just lint-frontend`, `just test-frontend`, `pnpm --dir frontend build`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): invitation acceptance and password reset pages"
```

---

### Task 15: Frontend — каркас кабинета

**Files:**
- Create: `frontend/src/components/app-header.tsx`, `frontend/src/components/logout-button.tsx`, `frontend/src/app/cabinet/layout.tsx`, `frontend/src/app/cabinet/cabinet-shell.tsx`, `frontend/src/app/cabinet/page.tsx`, `frontend/src/app/cabinet/home.tsx`, `frontend/src/app/cabinet/children/page.tsx`, `frontend/src/app/cabinet/children/children-accounts.tsx`, `frontend/src/app/cabinet/children/children-accounts.test.tsx`, `frontend/src/app/cabinet/settings/page.tsx`, `frontend/src/app/cabinet/settings/change-password.tsx`, `frontend/src/app/cabinet/settings/change-password.test.tsx`

**Interfaces:**
- Consumes: `useGetMe`, `useLogout`, `useListMyChildren`, `useSetMyChildAccount`, `useChangePassword`, `applyApiErrors`, `PasswordField`.
- Produces:
  - `AppHeader({ title, nav, me }: { title: string; nav: { href: string; label: string }[]; me: MeResponse })` — название, навигация (активная ссылка подсвечена по `usePathname`), `display_name`, `LogoutButton`.
  - `LogoutButton` — `useLogout`, затем `queryClient.clear()` и `router.replace("/login")`.
  - `cabinet/layout.tsx` (серверный, `robots: { index: false }`) → `<CabinetShell>{children}</CabinetShell>`; `CabinetShell` (клиентский) грузит `useGetMe`; пока грузится — скелет; `role === "tutor"` → `router.replace("/admin")`. Навигация: «Главная» `/cabinet`, «Дети» `/cabinet/children` (только parent), «Настройки» `/cabinet/settings`.
  - `/cabinet` (`Home`): «Здравствуйте, {display_name}!»; parent — список детей из `me.children`; блок «Расписание занятий появится здесь в ближайшее время» (план 5).
  - `/cabinet/children` (`ChildrenAccounts`, только parent; child → `router.replace("/cabinet")`): карточка на каждого ребёнка — имя, текущий логин или «Логин не выдан», форма «Логин» + «Пароль» (≥ 6, ≤ 128), кнопка «Сохранить»; ошибки `username_taken`, `invalid_username`, `password_*` — под полями через `applyApiErrors`; успех — toast «Логин сохранён».
  - `/cabinet/settings` (`ChangePassword`): текущий пароль, новый, повтор; успех — toast «Пароль изменён».

- [ ] **Step 1: Написать падающие тесты**

```ts
test("родитель задаёт логин ребёнку", async () => { /* POST /api/me/children/{id}/account с {username, password}; после ответа видно новый логин */ });
test("ошибка username_taken под полем логина", async () => {});
test("смена пароля: неверный текущий пароль под полем", async () => { /* 422 invalid_current_password details.field */ });
test("смена пароля: новые пароли должны совпадать", async () => {});
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-frontend`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just lint-frontend`, `just test-frontend`, `pnpm --dir frontend build`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): cabinet shell, children logins, password change"
```

---

### Task 16: Frontend — каркас админки и управление семьями

**Files:**
- Create: `frontend/src/app/admin/layout.tsx`, `frontend/src/app/admin/admin-shell.tsx`, `frontend/src/app/admin/page.tsx`, `frontend/src/app/admin/families/page.tsx`, `frontend/src/app/admin/families/families-list.tsx`, `frontend/src/app/admin/families/create-family-dialog.tsx`, `frontend/src/app/admin/families/families-list.test.tsx`, `frontend/src/app/admin/families/[id]/page.tsx`, `frontend/src/app/admin/families/[id]/family-detail.tsx`, `frontend/src/app/admin/families/[id]/child-form-dialog.tsx`, `frontend/src/app/admin/families/[id]/child-account-dialog.tsx`, `frontend/src/app/admin/families/[id]/family-detail.test.tsx`

**Interfaces:**
- Consumes: хуки Task 9, `AppHeader`, `CopyLinkCard`, `applyApiErrors`.
- Produces:
  - `admin/layout.tsx` → `AdminShell`: `useGetMe`; не tutor → `router.replace("/cabinet")`. Навигация: «Обзор» `/admin`, «Семьи» `/admin/families`.
  - `/admin`: заглушка дашборда «Заявки, расписание и запросы на перенос появятся в следующих версиях» и ссылка «Перейти к семьям».
  - `/admin/families` (`FamiliesList`): поиск (debounce 300 мс, параметр `q` в URL), переключатель «Архив» (`archived` в URL), таблица: семья, родители, активные дети; строка ведёт на `/admin/families/{id}`; кнопка «Новая семья» → `CreateFamilyDialog` (название, комментарий) → после создания переход на карточку.
  - `/admin/families/[id]` (`FamilyDetail`, `useParams`):
    - шапка: название и комментарий (редактирование в диалоге), бейдж «В архиве», кнопка «В архив» / «Вернуть из архива» с подтверждением;
    - «Родители»: таблица (ФИО, телефон, email, последний вход, статус), действия «Ссылка для смены пароля» (→ `CopyLinkCard` в диалоге) и «Заблокировать» / «Разблокировать»; если родителей нет и нет активного приглашения — подсказка «Создайте ссылку-приглашение и отправьте её родителю»;
    - «Приглашение»: кнопка «Создать ссылку-приглашение» (необязательные ФИО и телефон для предзаполнения) → `CopyLinkCard`; если есть `pending_invitation` — строка «Ссылка отправлена, действует до …» и предупреждение, что новая ссылка отменит прежнюю;
    - «Дети»: карточки (имя, год рождения, уровень, ссылка на занятие, логин), действия «Изменить» (`ChildFormDialog`), «Логин и пароль» (`ChildAccountDialog`), «Ссылка для смены пароля» (если есть учётка), «В архив» / «Вернуть»; кнопка «Добавить ребёнка».
    - Все ошибки форм — через `applyApiErrors`; успешные действия — toast; после мутаций инвалидируется запрос карточки семьи.

- [ ] **Step 1: Написать падающие тесты**

```ts
// families-list.test.tsx
test("поиск передаёт q в запрос", async () => { /* ввод "анна" → после debounce fetch с ?q=анна&archived=false */ });
test("создание семьи ведёт на её карточку", async () => { /* POST → router.push("/admin/families/<id>") */ });

// family-detail.test.tsx
test("создание приглашения показывает ссылку для копирования", async () => {});
test("архивация требует подтверждения", async () => { /* PATCH отправляется только после «Да, в архив» */ });
test("ошибка username_taken в диалоге логина ребёнка", async () => {});
test("подсказка про приглашение, если родителей нет", async () => {});
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-frontend`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just lint-frontend`, `just test-frontend`, `pnpm --dir frontend build`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): admin shell and family management"
```

---

### Task 17: Сквозная ручная проверка и документация

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: всё выше; dev-стек (`just dev`, `just web`).
- Produces: раздел README «Первый запуск: репетитор, семья, приглашение» (команды и шаги ниже).

- [ ] **Step 1: Поднять стек**

Run: `just dev`, затем `just migrate`, затем `just web` (в фоне)
Expected: `/api/health/ready` → `ok`; `http://localhost:3000/login` открывается.

- [ ] **Step 2: Пройти сценарий во встроенном браузере (`http://localhost:3000`)**

1. Войти репетитором (`tutor@example.com`, создан в плане 1; если нет — `just create-tutor`). Ожидается переход на `/admin`.
2. `/admin/families` → «Новая семья» «Тестовые» → карточка семьи.
3. «Добавить ребёнка» «Маша», уровень A2 → карточка ребёнка видна.
4. «Создать ссылку-приглашение» → скопировать URL.
5. Выйти; открыть URL приглашения; заполнить форму с согласием → попасть в `/cabinet`, видно «Маша».
6. `/cabinet/children` → выдать Маше логин `masha.test` / пароль из 6+ символов.
7. Выйти; войти как `masha.test` → `/cabinet`, в навигации нет «Дети».
8. Открыть `http://localhost:3000/admin` под ребёнком → редирект на `/cabinet`; `GET /api/admin/families` во вкладке → 404.
9. Войти репетитором, архивировать семью; повторный вход родителя → «Неверный логин или пароль».
10. Шесть неверных попыток входа подряд → сообщение о лимите попыток.

Expected: каждый шаг ведёт себя как описано; консоль браузера без ошибок (кроме ожидаемых 401/404 сетевых ответов).

- [ ] **Step 3: Записать раздел в README; прогнать всё**

Run: `just lint`, `just test`, `just gen-api`, затем `git status --short`
Expected: всё зелёное, дерево чистое после `gen-api`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: first-run walkthrough for tutor, family and invitation"
```
