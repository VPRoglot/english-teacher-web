# План 6 из 7: запросы на перенос и отмену, дашборд — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенос и отмена занятия проходят через кабинет. Родитель подаёт запрос с предупреждением о поздней отмене, репетитор получает Telegram-уведомление и одобряет или отклоняет запрос в очереди админки. Админка открывается дашбордом: новые заявки, ждущие запросы, занятия «нужно отметить», занятия сегодня.

**Architecture:**
- **Backend.**
  - `change_requests` живут в модуле `lessons` (спека 2.4): модель и сервис `app/lessons/requests_service.py`, эндпоинты в существующих `cabinet_router` / `admin_router`.
  - Уведомление — задача `notifications.notify_change_request`, идемпотентная через `change_requests.notified_at` (как `notify_new_lead`).
  - Дашборд — новый модуль `app/dashboard` (только чтение: сервисы `leads` и `lessons`, правило R8 из плана 5).
  - Архив ребёнка или семьи завершает его серии: роутер `families` после архивирования вызывает сервис `lessons` (сервис `families` не импортирует `lessons`, цикла нет).
- **Frontend.**
  - Кабинет: блок запроса на `/cabinet/lessons/[id]`.
  - Админка: очередь `/admin/requests`, дашборд `/admin`, мелкие правки карточки занятия и страницы семьи.

**Tech Stack:** как в плане 5, новых зависимостей нет.

**Spec:** `docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md` — используются разделы:
- 1.2 п.4; 3.3 (`change_requests`, «Поздняя отмена», правило удаления);
- 4.3 (`/me/lessons/{id}`, `/me/lessons/{id}/change-requests`, `/me/change-requests/{id}`), 4.4 (`/admin/dashboard`, `/admin/change-requests*`), 4.5 п.5;
- 5.1 (`/admin`, `/admin/requests`, `/cabinet/lessons/[id]`);
- 6.2, 6.5 (частичный уникальный индекс, `FOR UPDATE`);
- 7.1 (поздняя отмена; ребёнок не может создать запрос), 7.2 (предупреждение о поздней отмене);
- 9 п.6.

**Предыдущие планы:** 1–5 выполнены, код в `main`. Журнал плана 5: `docs/superpowers/ledgers/2026-10-12-05-lessons.md` (правила R4–R8, отложенные мелочи). Перенесено сюда из плана 5: запрет удалять занятие с запросами, активный запрос в `/me/lessons/{id}`, завершение серий при архиве ребёнка или семьи.

**Уточнения спеки, принятые в этом плане:**
1. **«Занятие с запросом»** — занятие, у которого есть хотя бы одна строка `change_requests` в любом статусе. Такое занятие не удаляется ни `DELETE /admin/lessons/{id}` (409 `lesson_not_deletable`), ни архивом серии, ни правкой серии (`reconcile_series` считает его «сохраняемым», как отсоединённое). FK `change_requests.lesson_id` — `ON DELETE RESTRICT`. Смена пояса (`shift_series_timezone`) такие занятия сдвигает: местное время то же.
2. **Поздняя отмена** вычисляется по моменту подачи запроса: `is_late = starts_at - created_at < cancel_policy_hours`. Порог читается при одобрении (а для предупреждения — при показе). Одобрение отмены ставит `cancelled_late`, если `is_late`, иначе `cancelled`.
3. **Одобрение и отклонение возможны только для `pending`**, иначе 409 `change_request_not_pending`. Одобрение требует, чтобы занятие было `scheduled`; иначе 409 `change_request_outdated` («Занятие уже изменено — отклоните запрос с комментарием»). Срок занятия при одобрении не проверяется: репетитор может одобрить отмену прошедшего занятия, о котором его предупредили заранее.
4. **Одобрение переноса:**
   - `new_starts_at` обязателен (422 на поле);
   - занятие получает новое время;
   - `is_detached = true`, если оно из серии;
   - нарушение `uq_lessons_series_id_starts_at` → 409 `lesson_slot_taken`;
   - ответ содержит `warnings` о пересечениях.
5. **Отзыв запроса** доступен любому родителю семьи, пока запрос `pending` (родители семьи равноправны); статус `withdrawn`, `resolved_at = now`.
6. **В кабинете** `/me/lessons/{id}` отдаёт `change_request` — последний запрос занятия (любой статус) в схеме для семьи. Так родитель видит и ждущий запрос, и ответ репетитора на отклонённый. Ребёнок видит запрос, но кнопок у него нет.
7. **Telegram-сообщение о запросе** — без комментария родителя (он может содержать лишнее; репетитор читает его в админке). Политика конфиденциальности дополняется строкой об уведомлениях о запросах.
8. **Дашборд:**
   - новые заявки: `new`, до 5 последних + общее число;
   - ждущие запросы: до 5 старейших + общее число;
   - «нужно отметить»: `scheduled` с `starts_at < now`, до 10 старейших + общее число;
   - сегодня: все занятия текущего дня в поясе репетитора, кроме отменённых.
9. **Архив ребёнка** (`PATCH /admin/children/{id}` с `archived: true`) и **архив семьи** (`PATCH /admin/families/{id}` с `archived: true`) завершают все активные серии затронутых детей тем же правилом, что `DELETE /admin/series/{id}`, плюс уточнение 1. Возврат из архива серии не восстанавливает.

## Global Constraints

- **Всё из планов 1–5 действует:**
  - Python 3.12, префикс `/api`, UUIDv7, `timestamptz` в UTC;
  - единый формат ошибок, русские тексты;
  - ruff, mypy strict, eslint, tsc; покрытие ≥ 85%;
  - сессия только через `DbSession`, в worker — `state.sessionmaker`;
  - после изменения API — `just gen-api` и коммит `frontend/openapi.json` + `frontend/src/api/generated/**`;
  - имена обработчиков = operationId;
  - `/admin/*` для не-репетитора → 404, без сессии → 401;
  - задачи идемпотентны;
  - ставить задачу в очередь только после `commit`; ошибка постановки логируется и не ломает ответ;
  - коммиты заканчиваются строкой `Co-Authored-By: <модель> <noreply@anthropic.com>`.
- **Порядок блокировок** (план 5): настройки → серия → занятие → запрос.
- **Тесты не зависят от реальных часов:** во frontend — `vi.useFakeTimers({ toFake: ["Date"] })`, в backend — `get_now` / явный `now`.
- **Модель** (спека 3.3, дословно, плюс `notified_at`):
  ```
  change_requests  id, lesson_id → lessons, requested_by → users, type (reschedule|cancel),
                   proposed_text NULL, comment NULL,
                   status (pending|approved|rejected|withdrawn),
                   tutor_response NULL, resolved_at NULL
                   UNIQUE (lesson_id) WHERE status = 'pending'
                   + notified_at NULL
  ```
- **Сценарий** (спека 4.5 п.5, дословно):
  - Родитель открывает занятие и выбирает «Запросить отмену» или «Запросить перенос».
  - Если до начала меньше `cancel_policy_hours`, интерфейс заранее предупреждает, что отмена будет засчитана как проведённое занятие.
  - Создаётся `change_request(pending)`, репетитор получает уведомление в Telegram.
  - Одобрение отмены: статус занятия становится `cancelled` или `cancelled_late` в зависимости от времени подачи запроса.
  - Одобрение переноса: репетитор указывает `new_starts_at`, занятие получает новое время и `is_detached = true`.
  - Отклонение: обязателен `tutor_response`, его видит родитель.
  - Одобрение выполняется в транзакции с `SELECT … FOR UPDATE` по запросу и занятию.
- **Запрос** можно подать только для будущего занятия в статусе `scheduled` (спека 4.3); ребёнок создать запрос не может.

## Review Focus

1. **Гонки вокруг одного занятия:**
   - двойной клик «Запросить отмену» → второй ответ 409 `change_request_exists`, запрос один (частичный уникальный индекс + блокировка занятия);
   - одновременные «Одобрить» и «Отозвать» → ровно один исход.
   
   Тесты в Task 2 и Task 4.
2. **Граница поздней отмены:**
   - запрос за 24 ч 1 мин до начала при пороге 24 → `cancelled`; за 23 ч 59 мин → `cancelled_late`;
   - порог 0 → никогда не поздняя;
   - решает момент подачи, а не одобрения (одобрение через 2 дня не делает отмену поздней).
   
   Тесты в Task 2 (чистая функция) и Task 4.
3. **Права:**
   - ребёнок → 404 на `POST /me/lessons/{id}/change-requests` и `DELETE /me/change-requests/{id}`;
   - родитель семьи B → 404 на занятие и запрос семьи A;
   - пробное занятие → 404;
   - `comment` и `tutor_response` видны семье, но в ответах семьи нет `requested_by` других пользователей и нет `private_text`.
   
   Тесты в Task 2.
4. **Занятие с запросом не исчезает:** архив серии, правка серии с другими днями и `DELETE /admin/lessons/{id}` оставляют занятие с отклонённым запросом на месте. Тесты в Task 1.
5. **Устаревший запрос:** репетитор сам отменил занятие через `PATCH`, затем жмёт «Одобрить перенос» → 409 `change_request_outdated`, занятие не изменилось; «Отклонить» по-прежнему работает. Тест в Task 4.

---

## Структура файлов

```
backend/app/
├── lessons/
│   ├── models.py               # + ChangeRequest, ChangeRequestType, ChangeRequestStatus
│   ├── late_cancel.py          # is_late_cancel() — чистая функция
│   ├── requests_service.py     # создание, отзыв, список, одобрение, отклонение, lesson_ids_with_requests
│   ├── schemas.py              # + схемы запросов (семья и админ)
│   ├── errors.py               # + ошибки запросов
│   ├── generation.py           # reconcile: занятие с запросом — сохраняемое
│   ├── series_service.py       # archive_series / archive_child_series не удаляют занятия с запросами
│   ├── service.py              # delete_lesson, has_requests в деталях, change_request для семьи
│   ├── cabinet_router.py, admin_router.py
├── notifications/tasks.py      # + notify_change_request
├── dashboard/{__init__,schemas,service,router}.py
├── families/admin_router.py    # архив → series_service.archive_child_series
└── main.py
backend/migrations/versions/0006_change_requests.py

frontend/src/
├── app/cabinet/lessons/[id]/{change-request-block,change-request-dialog}.tsx (+ тесты)
├── lib/change-request-format.ts (+ test)
├── app/admin/requests/{page,requests-queue,approve-dialog,reject-dialog}.tsx (+ тесты)
├── app/admin/{page,dashboard}.tsx (+ test)
├── app/admin/admin-shell.tsx   # пункт «Запросы»
├── app/admin/lessons/[id]/lesson-detail.tsx   # has_requests, ссылка на запрос
├── app/admin/families/[id]/…   # тексты подтверждения архива
└── components/site/privacy-policy.tsx
```

---

### Task 1: Модель запросов, миграция 0006 и защита занятий с запросами

**Files:**
- Modify: `backend/app/lessons/models.py`, `backend/app/lessons/generation.py`, `backend/app/lessons/series_service.py`, `backend/app/lessons/service.py`, `backend/app/lessons/schemas.py`, `backend/migrations/env.py` (если нужно)
- Create: `backend/migrations/versions/0006_change_requests.py`, `backend/app/lessons/requests_service.py` (пока только `lesson_ids_with_requests`)
- Test: `backend/tests/lessons/test_change_request_model.py`, `test_request_guards.py`; фабрика `make_change_request` в `tests/lessons/conftest.py`

**Interfaces:**
- Produces:
  - **Перечисления:**
    - `ChangeRequestType(StrEnum)`: `RESCHEDULE="reschedule"`, `CANCEL="cancel"`;
    - `ChangeRequestStatus(StrEnum)`: `PENDING`, `APPROVED`, `REJECTED`, `WITHDRAWN` (значения в нижнем регистре);
    - PG enum `change_request_type`, `change_request_status`.
  - **`ChangeRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base)`**, таблица `change_requests`:
    - `lesson_id` → `lessons.id` `ondelete="RESTRICT"`, с индексом;
    - `requested_by` → `users.id` `ondelete="RESTRICT"`;
    - `type`, `proposed_text` String(500) NULL, `comment` String(1000) NULL;
    - `status` default `pending`, `tutor_response` String(1000) NULL;
    - `resolved_at` NULL, `notified_at` NULL;
    - `Index("uq_change_requests_lesson_pending", "lesson_id", unique=True, postgresql_where=status == 'pending')`;
    - CHECK `resolved_consistent`: `(status = 'pending') = (resolved_at IS NULL)`;
    - CHECK `rejection_has_response`: `status <> 'rejected' OR tutor_response IS NOT NULL`.
  - **`requests_service.lesson_ids_with_requests(session, lesson_ids: Collection[UUID]) -> set[UUID]`** — id занятий, у которых есть запрос в любом статусе.
  - **Защита (уточнение 1):**
    - `service.delete_lesson`: занятие с запросом → `LessonNotDeletable`;
    - `series_service.archive_series`: удаление дополняется `~exists(change_requests where lesson_id = lessons.id)`;
    - `generation.reconcile_series`: занятие с запросом не «заменяемое» (не правится и не удаляется, дата занята — новое не создаётся). Множество берётся одним запросом через `lesson_ids_with_requests` после блокировки строк.
  - **`AdminLessonDetail.has_requests: bool`** — для кнопки «Удалить» и ссылки на очередь.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/lessons/test_change_request_model.py
async def test_one_pending_per_lesson(db_session) -> None:
    # два pending на одно занятие → IntegrityError; pending + rejected → можно
async def test_resolved_at_matches_status(db_session) -> None: ...   # pending с resolved_at → IntegrityError
async def test_rejected_needs_response(db_session) -> None: ...
async def test_lesson_with_request_cannot_be_deleted_at_db_level(db_session) -> None: ...  # RESTRICT

# tests/lessons/test_request_guards.py
async def test_delete_lesson_with_request_is_409(tutor_client, db_session) -> None:
    # будущее scheduled занятие + rejected запрос → DELETE 409 lesson_not_deletable
async def test_archive_series_keeps_lessons_with_requests(tutor_client, db_session) -> None: ...
async def test_series_edit_keeps_lesson_with_request(tutor_client, db_session) -> None:
    # правка «с даты» со сменой дней: занятие с запросом осталось (время, серия прежние), двойника на его дату нет
async def test_admin_detail_reports_has_requests(tutor_client, db_session) -> None: ...
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/lessons tests/test_migrations.py --no-cov`
Expected: FAIL — нет `ChangeRequest`.

- [ ] **Step 3: Реализовать по Interfaces** (миграция в стиле 0005; `downgrade` удаляет таблицу, затем enum)

- [ ] **Step 4: Тесты, линтеры, клиент**

Run: `just test-backend`, `just lint-backend`, `just gen-api`, `just lint-frontend`
Expected: зелёное, включая `test_models_match_migrations`.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(backend): change request model and protection of lessons with requests"
```

---

### Task 2: Запросы из кабинета — создание, отзыв, запрос в карточке занятия

**Files:**
- Create: `backend/app/lessons/late_cancel.py`
- Modify: `backend/app/lessons/requests_service.py`, `schemas.py`, `errors.py`, `service.py` (`get_family_lesson`), `cabinet_router.py`
- Test: `backend/tests/lessons/test_late_cancel.py`, `test_cabinet_requests.py`, `test_request_access.py`

**Interfaces:**
- Consumes: `FamilyScopeDep`, `ParentUser`, `_lock_lesson`, `get_tutor_settings`, `TaskQueueDep`.
- Produces:
  - **`is_late_cancel(*, requested_at: datetime, starts_at: datetime, policy_hours: int) -> bool`** — `starts_at - requested_at < timedelta(hours=policy_hours)`.
  - **Ошибки:**
    - `ChangeRequestNotFound(NotFound)` — `change_request_not_found`, «Запрос не найден»;
    - `ChangeRequestExists(Conflict)` — `change_request_exists`, «По этому занятию уже есть запрос — дождитесь ответа репетитора»;
    - `LessonNotRequestable(Conflict)` — `lesson_not_requestable`, «Запрос можно подать только по будущему запланированному занятию»;
    - `ChangeRequestNotPending(Conflict)` — `change_request_not_pending`, «Запрос уже рассмотрен или отозван».
  - **Схемы:**
    - `ChangeRequestCreate`:
      - `type: ChangeRequestType`;
      - `proposed_text: str | None` ≤ 500 — для `reschedule` обязателен, непустой после strip, ошибка на поле «Укажите удобное время»; для `cancel` должен отсутствовать или быть пустым (пустое → `None`);
      - `comment: str | None` ≤ 1000;
      - `extra="forbid"`.
    - `ChangeRequestForFamily`: `id`, `type`, `status`, `proposed_text`, `comment`, `tutor_response`, `created_at`, `resolved_at`, `is_late: bool` (для `cancel` — по уточнению 2, для `reschedule` — `False`).
    - `LessonForFamilyDetail` + `change_request: ChangeRequestForFamily | None` (последний по `created_at`).
  - **Сервис:**
    - `create_change_request(session, child_ids, lesson_id, data, *, user: User, now) -> ChangeRequestForFamily`:
      - блокирует занятие (`_lock_lesson`);
      - вне области или пробное → `LessonNotFound`;
      - не `scheduled` или `starts_at <= now` → `LessonNotRequestable`;
      - есть `pending` → `ChangeRequestExists`; гонку, прошедшую мимо проверки, ловит индекс → тот же 409 (вставка под `begin_nested()`);
    - `withdraw_change_request(session, child_ids, request_id, *, now) -> ChangeRequestForFamily` — блокирует запрос (`FOR UPDATE`), вне области → `ChangeRequestNotFound`, не `pending` → `ChangeRequestNotPending`;
    - `NOTIFY_CHANGE_REQUEST_TASK = "notifications.notify_change_request"`; `request_change_notification(queue, request_id)` — по образцу `request_lead_notification`.
  - **Роутер (`/me`):**
    - `POST /me/lessons/{lesson_id}/change-requests` (201, `ParentUser`) → `create_change_request`; после `commit` ставит задачу;
    - `DELETE /me/change-requests/{request_id}` (`ParentUser`) → `withdraw_change_request` → 200 `ChangeRequestForFamily`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/lessons/test_late_cancel.py
START = datetime(2026, 10, 20, 15, tzinfo=UTC)
@pytest.mark.parametrize("before,policy,late", [
    (timedelta(hours=24, minutes=1), 24, False), (timedelta(hours=23, minutes=59), 24, True),
    (timedelta(hours=24), 24, False), (timedelta(minutes=5), 0, False), (timedelta(hours=2), 12, True)])
def test_is_late_cancel(before, policy, late) -> None:
    assert is_late_cancel(requested_at=START - before, starts_at=START, policy_hours=policy) is late

# tests/lessons/test_cabinet_requests.py
async def test_parent_requests_cancel_and_sees_it_on_lesson(parent_client, db_session, task_queue) -> None:
    r = await parent_client.post(f"/api/me/lessons/{lesson.id}/change-requests", json={"type": "cancel", "comment": "Заболела"})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert task_queue.calls == [("notifications.notify_change_request", {"request_id": r.json()["id"]})]
    detail = (await parent_client.get(f"/api/me/lessons/{lesson.id}")).json()
    assert detail["change_request"]["comment"] == "Заболела"

async def test_reschedule_requires_proposed_text(parent_client, db_session) -> None: ...  # 422 loc ["body","proposed_text"]
async def test_second_pending_is_409(parent_client, db_session) -> None: ...             # 201, затем 409 change_request_exists
@pytest.mark.parametrize("case", ["past", "cancelled", "completed"])
async def test_only_future_scheduled_lessons(parent_client, db_session, case) -> None: ...  # 409 lesson_not_requestable
async def test_withdraw_then_new_request_allowed(parent_client, db_session) -> None: ...
async def test_withdraw_resolved_is_409(parent_client, db_session) -> None: ...
async def test_late_flag_uses_request_time(parent_client, db_session) -> None:
    # порог 24, занятие через 10 ч → is_late True в ответе и в карточке
async def test_request_saved_even_if_enqueue_fails(parent_client, db_session, task_queue) -> None: ...

# tests/lessons/test_request_access.py
async def test_child_cannot_create_or_withdraw(child_client, db_session) -> None: ...   # оба 404
async def test_other_family_gets_404(parent_client, db_session) -> None: ...            # занятие и запрос семьи B
async def test_trial_lesson_not_requestable(parent_client, db_session) -> None: ...     # 404
async def test_family_response_has_no_private_fields(parent_client, child_client, db_session) -> None:
    # в сыром JSON /me/lessons/{id} нет "private", "requested_by", текста приватной заметки
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/lessons --no-cov`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Тесты, линтеры, клиент**

Run: `just test-backend`, `just lint-backend`, `just gen-api`, `just lint-frontend`
Expected: зелёное; хуки `useCreateChangeRequest`, `useWithdrawChangeRequest`.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(backend): reschedule and cancel requests from the family cabinet"
```

---

### Task 3: Telegram-уведомление о запросе

**Files:**
- Modify: `backend/app/notifications/tasks.py`, `frontend/src/components/site/privacy-policy.tsx` (+ её тест)
- Test: `backend/tests/notifications/test_notify_change_request.py`

**Interfaces:**
- Consumes: `NOTIFY_CHANGE_REQUEST_TASK` из `app.lessons.requests_service`, модели `ChangeRequest`, `Lesson`, `Child`, `TutorSettings` (чтение, R8), `is_late_cancel`, `state.notifier`, `state.public_base_url`.
- Produces:
  - **`format_change_request_message(*, type, child_name, starts_at_local: str, is_late: bool, admin_url: str) -> str`**, обычный текст:
    ```
    Запрос на {перенос|отмену} занятия
    Ученик: {child_name}
    Занятие: {dd.MM.yyyy HH:mm}
    Поздняя отмена            ← только если is_late
    {admin_url}
    ```
    `admin_url = {public_base_url}/admin/requests`. Время — в поясе репетитора.
  - **`notify_change_request(request_id: str, context)`** — копия логики `notify_new_lead`:
    - `FOR UPDATE` по запросу;
    - нет запроса, уже `notified_at` или запрос не `pending` → info-лог и выход;
    - `DisabledNotifier` → warning `change_request_notification_skipped` (`notified_at` остаётся пустым);
    - иначе отправка, `notified_at = now`, `commit`.
  - **Регистрация** в `register_tasks`.
  - **Политика конфиденциальности:** к абзацу о Telegram добавить «…а также уведомления о запросах на перенос и отмену занятий (имя ученика и время занятия)».

- [ ] **Step 1: Написать падающие тесты**

```python
def test_message_for_late_cancel() -> None:
    text = format_change_request_message(type=ChangeRequestType.CANCEL, child_name="Маша", starts_at_local="20.10.2026 18:00",
                                         is_late=True, admin_url="https://t.example/admin/requests")
    assert text.splitlines() == ["Запрос на отмену занятия", "Ученик: Маша", "Занятие: 20.10.2026 18:00",
                                 "Поздняя отмена", "https://t.example/admin/requests"]
async def test_sends_once_in_tutor_timezone(worker_state, db_request) -> None: ...  # пояс Asia/Yekaterinburg → время YEKT
async def test_resolved_or_missing_request_is_noop(worker_state, db_session) -> None: ...
async def test_failure_leaves_unnotified(worker_state, db_request) -> None: ...
async def test_disabled_notifier_keeps_notified_at_null(worker_state, db_request) -> None: ...
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/notifications --no-cov`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-backend`, `just lint-backend`, `pnpm --dir frontend exec vitest run src/components/site/privacy-policy.test.tsx`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/src/components/site
git commit -m "feat(backend): notify the tutor in Telegram about change requests"
```

---

### Task 4: Очередь запросов в админ-API — список, одобрение, отклонение

**Files:**
- Modify: `backend/app/lessons/requests_service.py`, `schemas.py`, `errors.py`, `admin_router.py`
- Test: `backend/tests/lessons/test_admin_requests.py`

**Interfaces:**
- Consumes: `_lock_lesson`, `find_overlaps`, `get_tutor_settings`, `is_late_cancel`, `LessonSlotTaken`, `OverlapWarning`, `Now`.
- Produces:
  - **Ошибка:** `ChangeRequestOutdated(Conflict)` — `change_request_outdated`, «Занятие уже изменено — отклоните запрос с комментарием».
  - **Схемы:**
    - `ChangeRequestAdminItem`:
      - `id`, `type`, `status`, `proposed_text`, `comment`, `tutor_response`, `created_at`, `resolved_at`, `is_late`;
      - `lesson: {id, starts_at, duration_min, status}`;
      - `child: {id, full_name}`, `family: {id, name}`;
      - `requested_by_name: str` (ФИО родителя из `parent_profiles`).
    - `ChangeRequestApprove`: `new_starts_at: AwareDatetime | None = None`.
    - `ChangeRequestReject`: `tutor_response: str` 1..1000 (strip; пустое → 422 «Напишите ответ родителю»).
    - `ChangeRequestResolved(ChangeRequestAdminItem)`: `warnings: list[OverlapWarning]`.
  - **Сервис:**
    - `list_admin_requests(session, *, status: ChangeRequestStatus | None) -> list[ChangeRequestAdminItem]` — `pending` по `created_at` asc, остальные по `resolved_at` desc, не больше 200;
    - `approve_change_request(session, request_id, data, *, now) -> ChangeRequestResolved`:
      - порядок блокировок из Global Constraints: `lesson_id` запроса читается без блокировки, затем `FOR UPDATE` занятия, затем `FOR UPDATE` запроса (`populate_existing`); нет запроса → `ChangeRequestNotFound`;
      - не `pending` → `ChangeRequestNotPending`; занятие не `scheduled` → `ChangeRequestOutdated`;
      - `cancel` → статус занятия по уточнению 2 (порог из настроек на момент одобрения);
      - `reschedule` без `new_starts_at` → 422 на `["body","new_starts_at"]` «Укажите новое время»; иначе новое время, `is_detached` для серии, 409 `lesson_slot_taken` под savepoint, пересечения;
      - запрос: `approved`, `resolved_at = now`;
    - `reject_change_request(session, request_id, data, *, now) -> ChangeRequestResolved` — блокировка запроса, не `pending` → 409; `rejected`, `tutor_response`, `resolved_at`.
  - **Роутер:**
    - `GET /admin/change-requests?status=` (по умолчанию `pending`) → `list_change_requests`;
    - `POST /admin/change-requests/{request_id}/approve` → `approve_change_request`;
    - `POST /admin/change-requests/{request_id}/reject` → `reject_change_request`.

- [ ] **Step 1: Написать падающие тесты**

```python
async def test_list_pending_oldest_first_with_context(tutor_client, db_session) -> None: ...
async def test_approve_cancel_on_time(tutor_client, db_session) -> None:
    # запрос подан за 30 ч при пороге 24 → занятие cancelled, запрос approved, resolved_at задан
async def test_approve_cancel_late_uses_request_time(tutor_client, db_session) -> None:
    # подан за 10 ч, одобрен когда угодно → cancelled_late
async def test_approve_reschedule_detaches_and_warns(tutor_client, db_session) -> None:
    # серия; new_starts_at → starts_at, is_detached True; пересечение → warnings[0].code == "overlap"
async def test_reschedule_without_time_is_422(tutor_client, db_session) -> None: ...
async def test_reject_requires_response_and_family_sees_it(tutor_client, parent_client, db_session) -> None: ...
async def test_outdated_request_cannot_be_approved_but_can_be_rejected(tutor_client, db_session) -> None:
    # PATCH занятия status=cancelled; approve → 409 change_request_outdated, занятие без изменений; reject → 200
async def test_resolve_twice_is_409(tutor_client, db_session) -> None: ...
async def test_withdrawn_cannot_be_approved(tutor_client, db_session) -> None: ...
async def test_slot_taken_on_reschedule_is_409(tutor_client, db_session) -> None: ...
@pytest.mark.parametrize("method,path", [...])   # три эндпоинта
async def test_requests_admin_only(client, parent_client, method, path) -> None: ...
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/lessons/test_admin_requests.py --no-cov`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Тесты, линтеры, клиент**

Run: `just test-backend`, `just lint-backend`, `just gen-api`, `just lint-frontend`
Expected: зелёное; хуки `useListChangeRequests`, `useApproveChangeRequest`, `useRejectChangeRequest`.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(backend): admin change request queue with approve and reject"
```

---

### Task 5: Архив ребёнка или семьи завершает серии

**Files:**
- Modify: `backend/app/lessons/series_service.py`, `backend/app/families/admin_router.py`
- Test: `backend/tests/lessons/test_archive_child_series.py`

**Interfaces:**
- Consumes: `archive_series` (правило удаления с уточнением 1), `lock_series`.
- Produces:
  - **`series_service.archive_child_series(session, child_ids: Collection[UUID], *, now: datetime) -> int`** — завершает каждую активную серию этих детей (блокировки серий в порядке id), возвращает число завершённых серий.
  - **`families/admin_router.update_family`:** если `body.archived is True` и семья перешла в архив в этом запросе, вызывает `archive_child_series` для всех детей семьи (id детей — через `families_service`).
  - **`update_child`:** то же при `archived is True` для одного ребёнка.
  - Возврат из архива серии не трогает.

- [ ] **Step 1: Написать падающие тесты**

```python
async def test_archiving_child_ends_series_and_future_lessons(tutor_client, db_session) -> None:
    # серия ребёнка + прошедшее занятие + будущее с запросом → PATCH /children/{id} archived → серия archived_at,
    # будущие scheduled удалены, прошедшее и занятие с запросом на месте
async def test_archiving_family_ends_all_children_series(tutor_client, db_session) -> None: ...
async def test_unarchive_does_not_restore_series(tutor_client, db_session) -> None: ...
async def test_repeat_archive_patch_is_harmless(tutor_client, db_session) -> None: ...
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/lessons/test_archive_child_series.py --no-cov`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Тесты и линтеры**

Run: `just test-backend`, `just lint-backend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): archiving a child or family ends its lesson series"
```

---

### Task 6: API дашборда

**Files:**
- Create: `backend/app/dashboard/__init__.py`, `schemas.py`, `service.py`, `router.py`
- Modify: `backend/app/main.py`, `backend/app/lessons/service.py` (функции для дашборда), `backend/app/lessons/requests_service.py`
- Test: `backend/tests/dashboard/__init__.py`, `test_dashboard.py`

**Interfaces:**
- Consumes: `leads_service.list_leads(status=NEW, limit=5, offset=0)`, `list_admin_requests`, `get_timezone`.
- Produces:
  - **`lessons_service.list_needs_marking(session, *, now, limit) -> tuple[list[AdminLessonItem], int]`** — `scheduled`, `starts_at < now`, старейшие первыми.
  - **`lessons_service.list_day_lessons(session, *, day_start, day_end) -> list[AdminLessonItem]`** — без `cancelled`/`cancelled_late`, по времени.
  - **`requests_service.pending_summary(session, *, limit) -> tuple[list[ChangeRequestAdminItem], int]`.**
  - **`DashboardResponse`:**
    - `new_leads: {items: list[LeadListItem], total: int}`;
    - `pending_requests: {items: list[ChangeRequestAdminItem], total: int}`;
    - `needs_marking: {items: list[AdminLessonItem], total: int}`;
    - `today: list[AdminLessonItem]`;
    - `timezone: str`.
  - **`GET /admin/dashboard`** → `get_dashboard` (с `Now` для тестов).

- [ ] **Step 1: Написать падающие тесты**

```python
async def test_dashboard_sections(tutor_client, db_session) -> None:
    # 6 новых заявок → 5 items, total 6; contacted не считается
    # 2 pending + 1 rejected → total 2, старейший первым
    # прошедшие scheduled (12 шт.) → 10 items, total 12; прошедшее completed не считается
    # сегодня в поясе репетитора: занятие 23:30 MSK входит, 00:30 следующего дня — нет; отменённое сегодня — нет
async def test_today_follows_tutor_timezone(tutor_client, db_session) -> None: ...   # Asia/Yekaterinburg
async def test_dashboard_admin_only(client, parent_client) -> None: ...
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `just test-backend tests/dashboard --no-cov`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Тесты, линтеры, клиент**

Run: `just test-backend`, `just lint-backend`, `just gen-api`, `just lint-frontend`
Expected: зелёное; хук `useGetDashboard`.

- [ ] **Step 5: Commit**

```bash
git add backend frontend/openapi.json frontend/src/api/generated
git commit -m "feat(backend): admin dashboard API"
```

---

### Task 7: Frontend — запрос в кабинете

**Files:**
- Create:
  - `frontend/src/lib/change-request-format.ts` (+ test);
  - `frontend/src/app/cabinet/lessons/[id]/change-request-block.tsx`, `change-request-dialog.tsx` (+ тесты).
- Modify: `frontend/src/app/cabinet/lessons/[id]/cabinet-lesson.tsx`

**Interfaces:**
- Consumes: `useGetMyLesson` (`change_request`), `useCreateChangeRequest`, `useWithdrawChangeRequest`, `useGetScheduleSettings` (`cancel_policy_hours`), `useGetMe` (роль), `formatDateTime`, `useTutorTimeZone("cabinet")`, `applyApiErrors`.
- Produces:
  - **`change-request-format.ts`:**
    - `CHANGE_REQUEST_TYPE_LABELS = { reschedule: "Перенос", cancel: "Отмена" }`;
    - `CHANGE_REQUEST_STATUS_LABELS = { pending: "Ждёт ответа репетитора", approved: "Одобрен", rejected: "Отклонён", withdrawn: "Отозван" }`;
    - `isLateNow(startsAt: string, policyHours: number, now: Date): boolean`.
  - **`ChangeRequestBlock({ lesson })`:**
    - есть `change_request`: тип, статус, предложенное время, комментарий, `tutor_response` (для `rejected` — «Ответ репетитора: …»), у отмены с `is_late` — пометка «Поздняя отмена»;
    - `pending` и роль `parent` → кнопка «Отозвать запрос» (`ConfirmDialog`);
    - нет `pending`, роль `parent`, занятие `scheduled` и в будущем → кнопки «Запросить перенос» и «Запросить отмену»;
    - ребёнок кнопок не видит.
  - **`ChangeRequestDialog({ type, lesson, open, onOpenChange })`:**
    - перенос: «Когда удобно?» (обязательно, textarea ≤ 500) и «Комментарий»;
    - отмена: «Комментарий»;
    - если `isLateNow(...)`: `Alert` «До занятия меньше {N} ч — отмена будет засчитана как проведённое занятие»; у переноса — «Если перенос не согласуют, занятие может быть засчитано как проведённое»;
    - успех → инвалидировать `/api/me/lessons…`, toast «Запрос отправлен репетитору»;
    - 409 → `Alert`.

- [ ] **Step 1: Написать падающие тесты**

```tsx
// change-request-format.test.ts
test("late when less than policy hours left", () => { /* фейковые часы; 23:59 до начала при 24 → true; 24:01 → false; порог 0 → false */ });
// change-request-block.test.tsx (фейковые часы)
test("parent sees request buttons for future scheduled lesson", async () => { ... });
test("child sees no buttons", async () => { ... });
test("pending request shows status and withdraw", async () => { /* DELETE /api/me/change-requests/{id} после подтверждения */ });
test("rejected request shows tutor response", async () => { ... });
// change-request-dialog.test.tsx
test("cancel within policy shows late warning", async () => { /* порог 24, до начала 10 ч → текст предупреждения */ });
test("reschedule requires proposed time", async () => { /* без текста fetch не вызван */ });
test("sends request and shows toast", async () => { /* POST {type:"cancel", comment} */ });
test("409 is shown", async () => { ... });
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend exec vitest run src/lib/change-request-format.test.ts "src/app/cabinet/lessons/\[id\]"`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-frontend`, `just lint-frontend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): reschedule and cancel requests in the family cabinet"
```

---

### Task 8: Frontend — очередь запросов `/admin/requests`

**Files:**
- Create: `frontend/src/app/admin/requests/page.tsx`, `requests-queue.tsx`, `approve-dialog.tsx`, `reject-dialog.tsx` (+ тесты)
- Modify: `frontend/src/app/admin/admin-shell.tsx` (пункт «Запросы» после «Календарь»), `frontend/src/lib/lesson-mutations.ts` (инвалидация `/api/admin/change-requests` и `/api/admin/dashboard` вместе с расписанием)

**Interfaces:**
- Consumes: `useListChangeRequests`, `useApproveChangeRequest`, `useRejectChangeRequest`, `LessonTimeFields`, `zonedToUtcIso`, `utcToZonedParts`, `useTutorTimeZoneStatus`, `formatLessonWhen`, `toastWarnings`, `invalidateSchedule`, `CHANGE_REQUEST_*_LABELS`.
- Produces:
  - **`RequestsQueue`:**
    - вкладки «Ждут ответа» (`?status=pending`, по умолчанию) и «Все» (без фильтра) через параметр URL `?tab=`;
    - карточка: ребёнок (ссылка на семью), «Занятие: {formatLessonWhen}» (ссылка на `/admin/lessons/{id}`), тип, «Поздняя отмена», предложенное время, комментарий, «{requested_by_name}, {дата подачи}»;
    - для `pending` — «Одобрить» и «Отклонить»; для остальных — статус, ответ, дата решения;
    - пусто: «Запросов нет».
  - **`ApproveDialog`:**
    - отмена: подтверждение «Занятие будет отменено» / «Отмена поздняя — занятие будет засчитано как проведённое»;
    - перенос: `LessonTimeFields` (дата и время в поясе репетитора, предзаполнены текущим временем занятия, длительность не показывается), пока пояс не загружен — submit неактивен (R5).
    - Успех → `invalidateSchedule` + запросы очереди и дашборда, toast «Запрос одобрен», предупреждения через `toastWarnings`.
    - 409 → `Alert`.
  - **`RejectDialog`:** обязательный «Ответ родителю» → toast «Запрос отклонён».

- [ ] **Step 1: Написать падающие тесты**

```tsx
test("lists pending requests with lesson context", async () => { ... });
test("approve reschedule sends UTC from tutor zone", async () => {
  // пояс Asia/Yekaterinburg, 21.10 20:00 → new_starts_at "2026-10-21T15:00:00.000Z"
});
test("approve late cancel warns before confirming", async () => { ... });
test("reject requires a response", async () => { ... });
test("outdated 409 is shown", async () => { ... });
test("tab all shows resolved requests", async () => { ... });
// admin-shell.test.tsx — пункт «Запросы»
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend exec vitest run src/app/admin/requests src/app/admin/admin-shell.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces** (`page.tsx` — `instant = false` + `Suspense`)

- [ ] **Step 4: Проверить**

Run: `just test-frontend`, `just lint-frontend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): admin change request queue"
```

---

### Task 9: Frontend — дашборд, карточка занятия, подтверждение архива

**Files:**
- Create: `frontend/src/app/admin/dashboard.tsx` (+ test)
- Modify:
  - `frontend/src/app/admin/page.tsx` (вместо заглушки — `Dashboard`);
  - `frontend/src/app/admin/lessons/[id]/lesson-detail.tsx` (+ test);
  - тексты подтверждения архива в `frontend/src/app/admin/families/[id]/family-detail.tsx` и в архиве ребёнка (`child-form-dialog.tsx` или где он сейчас).

**Interfaces:**
- Consumes: `useGetDashboard`, `LEAD_STATUS_LABELS`, `formatLessonWhen`, `formatDateTime`, `NEEDS_MARKING_LABEL`, `CHANGE_REQUEST_TYPE_LABELS`.
- Produces:
  - **`Dashboard`** — четыре карточки, у каждой заголовок с числом:
    - «Новые заявки» — родитель, возраст ребёнка, дата, ссылка на заявку; «Все заявки» → `/admin/leads?status=new`;
    - «Ждут ответа» — тип запроса, ребёнок, время занятия; «Открыть очередь» → `/admin/requests`;
    - «Нужно отметить» — ученик и время, ссылка на занятие;
    - «Сегодня» — время и ученик, ссылка на занятие; пусто — «Сегодня занятий нет».
    
    Пустые карточки показывают короткий текст («Новых заявок нет» и т. п.). Время — в поясе из ответа.
  - **`LessonDetail`:**
    - кнопка «Удалить» скрыта при `has_requests`;
    - при `has_requests` — строка «По занятию есть запрос семьи» со ссылкой «Открыть запросы» → `/admin/requests?tab=all`.
  - **Подтверждение архива** ребёнка и семьи дополняется фразой «Регулярные занятия будут завершены, будущие занятия удалены».

- [ ] **Step 1: Написать падающие тесты**

```tsx
test("dashboard shows counts and links", async () => { ... });
test("empty sections show placeholders", async () => { ... });
test("lesson with requests hides delete and links to queue", async () => { ... });
test("archive confirmation mentions series", async () => { ... });
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `pnpm --dir frontend exec vitest run src/app/admin/dashboard.test.tsx "src/app/admin/lessons/\[id\]" "src/app/admin/families/\[id\]"`
Expected: FAIL.

- [ ] **Step 3: Реализовать по Interfaces**

- [ ] **Step 4: Проверить**

Run: `just test-frontend`, `just lint-frontend`
Expected: зелёное.

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): admin dashboard, lesson request hint, archive confirmation"
```

---

### Task 10: Сквозная проверка и документация

**Files:**
- Modify: `README.md` (раздел «Запросы на перенос и отмену»)

**Interfaces:**
- Produces: в README — путь запроса (кабинет → очередь → решение), правило поздней отмены, Telegram-уведомление, дашборд, правило «занятие с запросом не удаляется».

- [ ] **Step 1: Полный прогон**

Run: `just lint`, `just test`
Expected: всё зелёное, покрытие backend ≥ 85%.

- [ ] **Step 2: Сборка без API**

Run: `just down`, затем `pnpm --dir frontend build`
Expected: сборка успешна, маршрут `/admin/requests` есть.

- [ ] **Step 3: Ручная проверка во встроенном браузере** (выполняет контроллер)

Expected:
1. Родитель (375 px): «Запросить отмену» за 10 ч до занятия при пороге 24 → предупреждение о поздней отмене. Запрос отправлен, в карточке «Ждёт ответа репетитора». Повторная кнопка недоступна.
2. Worker: `notify_change_request` → `telegram_disabled` / `change_request_notification_skipped` или сообщение в Telegram.
3. Репетитор: дашборд показывает запрос, «нужно отметить» и занятия сегодня. В `/admin/requests` одобрение отмены → занятие «Поздняя отмена».
4. Перенос: родитель предлагает время, репетитор одобряет с новым временем → в кабинете новое время, в админке бейдж «Перенесено».
5. Отклонение с ответом → родитель видит ответ репетитора.
6. Отзыв запроса родителем → можно подать новый.
7. Ребёнок: кнопок запроса нет.
8. Архив ребёнка → его серия завершена, будущие занятия исчезли из календаря, занятие с запросом осталось.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: change requests, late cancellation and dashboard"
```
