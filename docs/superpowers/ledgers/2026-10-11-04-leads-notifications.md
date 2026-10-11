# SDD ledger — plan: docs/superpowers/plans/2026-10-11-04-leads-notifications.md

BASE (branch start): 8c54300 (branch worktree-leads)
Spec: docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md
Context files: global.md, env-notes.md, implementer-contract.md, reviewer-contract.md (this dir)

## Pre-flight scan

| Пара / задача | Производит → потребляет | Результат |
|---|---|---|
| T1 ↔ (план 3 тесты) | `BrokerTaskQueue(broker, *, timeout_seconds)` → существующие вызовы `BrokerTaskQueue(broker)` в main.py и tests | T1 обязан обновить все вызовы; ок |
| T1 ↔ T4 | `state.sessionmaker`, `state.engine`, `state.http` → notify_new_lead | согласовано |
| T2 ↔ T3/T5 | `normalize_phone`, `Lead`, `LeadStatusHistory`, `LeadStatus`, `ContactMethod`, `can_transition`, `MANUAL_TARGETS` | согласовано |
| T3 ↔ T4 | `NOTIFY_NEW_LEAD_TASK` в `app.leads.service`, kwargs `lead_id: str` → задача | согласовано, цикла импортов нет |
| T3 ↔ T6 | handler `submit_lead` → `useSubmitLead`, zod `SubmitLeadBody` | согласовано |
| T3 ↔ T4 | Settings `telegram_*` (T3) → notifier в setup_worker (T4) | согласовано |
| T5 ↔ T7/T8 | handlers list_leads/get_lead/update_lead/convert_lead → useListLeads/useGetLead/useUpdateLead/useConvertLead, zod UpdateLeadBody/ConvertLeadBody | согласовано |
| T6 ↔ (план 3 landing tests) | `Landing({site, captchaKey})` → существующие тесты рендерят `<Landing site=…/>` | См. Ruling 1 |
| T8 ↔ T2 | `MANUAL_TRANSITIONS` во frontend — копия таблицы backend | дублирование таблицы между языками, план требует тест-сверку; приемлемо |
| T1 self | тесты ↔ интерфейсы (имена атрибутов taskiq-redis сверяются) | согласовано |
| T2 self | тесты фраз телефона ↔ правила плана 3 | согласовано |
| T3 self | порядок rate limit → honeypot → captcha ↔ тест honeypot (засчитывается в лимит) | согласовано |
| T4 self | worker_state фикстура ↔ savepoint db_session | на усмотрение исполнителя |
| T5 self | test_leads_admin_only пути с {id} | исполнитель подставляет id |
| T6 self | `consent` Literal + своё сообщение (backend) ↔ frontend zod из SubmitLeadBody | frontend добавляет русские сообщения сам (как zodOptions в плане 3) |
| T7, T8 self | согласовано |
| T9 self | шаг 3 — контроллер | См. Ruling 2 |

Ruling 1: `Landing` получает `captchaKey?: string | null` (по умолчанию null), чтобы тесты и вызовы плана 3 не ломались — если неверно: косметика.
Ruling 2: Task 9 шаг 3 (браузер) выполняет контроллер; исполнитель — шаги 1, 2, 4 — встроенный браузер доступен только контроллеру — если неверно: никакой цены.

## Tasks
Task 1: dispatched (implementer a5e2e5f42b409e816, sonnet; BASE 8c54300)
Task 1: implementer DONE (7d03b2f): consumer_id="0", maxlen/approximate, socket timeouts 5s via pool kwargs, BrokerTaskQueue timeout. Note: existing dev Redis group created with "$" must be deleted once by hand. Review dispatched (a8c489671f8761d95, sonnet) on 8c54300..7d03b2f
Task 1: review Approved. ⚠️ test run accepted from report (full suite re-runs later); group-from-start behaviour — Minor 1 below.
Task 1: minor (deferred): no integration test that group from "0" delivers a message kicked before startup
Task 1: minor (deferred): no test that main.py passes task_enqueue_timeout_seconds to BrokerTaskQueue
Task 1: minor (deferred): README/deploy note — drop existing "taskiq" consumer group once (created with "$") — carry to Task 9 docs
Task 1: complete (commits 8c54300..7d03b2f, review clean)
Task 2: dispatched (BASE 7d03b2f)
Task 2: implementer a2b5c014841c46699 (sonnet)
Task 2: implementer DONE (5670280); passive_deletes="all", enums create_type=False. Review dispatched (a8aa924347959540b, sonnet) on 7d03b2f..5670280
Task 2: review Approved. ⚠️ suite/migration tests accepted from report (re-run in later tasks).
Task 2: minor (deferred): TRANSITIONS mutable dict — MappingProxyType
Task 2: minor (deferred): no DB-level invalid-enum insert test
Note for T3/T5: Lead.history is lazy — eager-load (selectinload) in async code.
Task 2: complete (commits 7d03b2f..5670280, review clean)
Task 3: dispatched (BASE 5670280)
Task 3: implementer aeb6fc4bdf3395b09 (sonnet)
Task 3: implementer DONE (557ebb4): useSubmitLead {data: LeadCreate}, zod SubmitLeadBody; blank optionals→None; PydanticCustomError messages; export_openapi app_env="dev". Review dispatched (a3e6994aadfa9a4c7, sonnet) on 5670280..557ebb4
Task 3: review Approved. ⚠️ resolved: CSRF for anonymous form — apiFetch bootstraps /api/auth/csrf for unsafe methods (plan 2); real BrokerTaskQueue path covered by Task 1 tests; generated names reported (useSubmitLead, SubmitLeadBody).
Task 3: minor (deferred): captcha failures consume the 3/hour budget — frontend must show Retry-After message clearly
Task 3: minor (deferred): missing request.client → shared key lead:ip:unknown; plan 7 must enable forwarded headers (--proxy-headers)
Task 3: minor (deferred): lifespan test reads private verifier._client; get_captcha_verifier uncovered
Task 3: complete (commits 5670280..557ebb4, review clean)
Task 4: dispatched (BASE 557ebb4)
Task 4: implementer a0bf2661573f87b77 (sonnet)
Task 4: implementer DONE (65e83e8): invalid lead_id → noop; NotifyFailed from None hides token; N818 ignore. Truncation concern moot (goal≤1000, preferred_time≤200). Review dispatched (a228682e88334ea41, sonnet) on 557ebb4..65e83e8
Task 4: review Approved. ⚠️ concurrency of FOR UPDATE — code-reading only (deferred minor); request_id via RequestIdTaskMiddleware — verify in Task 9 walkthrough.
Task 4: minor (deferred): Telegram 429 retry_after ignored
Task 4: minor (deferred): truncation cuts the admin link if field caps ever grow — truncate goal instead / comment
Task 4: minor (deferred): no test that FOR UPDATE serializes concurrent deliveries
Task 4: complete (commits 557ebb4..65e83e8, review clean)
Task 5: dispatched (BASE 65e83e8)
Task 5: implementer a0f26e5ab7d1b1667 (sonnet)
Task 5: implementer DONE (0588a56): hooks useListLeads/useGetLead/useUpdateLead/useConvertLead ({leadId,data}); zod UpdateLeadBody/ConvertLeadBody; anonymized → 404; changed_at set in Python; code-before-tests. Review dispatched (a0a029544dcdf3572, sonnet) on 65e83e8..0588a56
Task 5: review Approved. ⚠️ resolved: DbSession rollback on error paths (core/db.py get_db_session rollback on exception); generated names consistent with route.name; concurrency → minor below.
Task 5: minor (deferred): double-convert test sequential — nothing guards FOR UPDATE (assert compiled FOR UPDATE or two-session test)
Task 5: minor (deferred): MANUAL_TARGETS unused in app; Literal duplicates it — pin with test or derive
Task 5: minor (deferred): PATCH with comment but no status silently drops comment
Task 5: minor (deferred): "Укажите причину отказа" message also for reason-without-rejected (brief-mandated)
Task 5: minor (deferred): code written before tests (process)
Task 5: minor (deferred): no tests: convert unknown lead 404, convert from rejected/converted; phone search "8 999…" doesn't match +7
Task 5: complete (commits 65e83e8..0588a56, review clean)
Task 6: dispatched (BASE 0588a56)
Task 6: implementer a6d1875542bddb11c (sonnet)
Task 6: implementer DONE_WITH_CONCERNS (a2f88a9): local zod messages in trial-form (avoid admin bundle), SMARTCAPTCHA_CLIENT_KEY to compose web → Task 9, 375px/real widget unverified → walkthrough. Review dispatched (a8f31d6606611874e, sonnet) on 0588a56..a2f88a9
Task 6: review Approved. ⚠️ resolved: client phone completeness (+7 → 11 digits, others 10–15) consistent with backend normalize_phone (mask turns 8…/9…/bare digits into +7); widget event order & 375px → Task 9 walkthrough; compose SMARTCAPTCHA_CLIENT_KEY → Task 9.
Task 6: minor (deferred, user-facing): captcha widget JS error/hang leaves form stuck in «Отправляем…» — handle onJavascriptError + timeout; error paths untested
Task 6: minor (deferred): onChallengeHidden leaves stale pending
Task 6: minor (deferred): caret jumps to end when editing middle of phone
Task 6: minor (deferred): consent error not linked via aria-describedby
Task 6: minor (deferred): zodOptions duplicated (trial-form vs site-form) — move to lib/zod-ru.ts
Task 6: complete (commits 0588a56..a2f88a9, review clean)
Task 7: dispatched (BASE a2f88a9)
Task 7: implementer ac6cf3d6150373707 (sonnet)
Task 7: first implementer hit session limit before writing anything; re-dispatched (a4fd493c3640241c2, sonnet; BASE a2f88a9)
Task 7: implementer DONE (4bd1eb9). Note: focused vitest = pnpm --dir frontend exec vitest run <paths>. Review dispatched (abcea1f0ec5350a00, sonnet) on a2f88a9..4bd1eb9
Task 7: review Approved. ⚠️ tsc/eslint accepted from report (Object.hasOwn — full lint re-run in Task 9); narrow-width table → walkthrough.
Task 7: minor (deferred): stale range text «101–150 из 120» during page transition (keepPreviousData) — use isPlaceholderData
Task 7: minor (deferred): page beyond last shows «Заявок пока нет» — clamp page
Task 7: minor (deferred): admin-shell test lacks «Заявки» nav assertion; «Назад» only tested 2→1
Task 7: complete (commits a2f88a9..4bd1eb9, review clean)
Task 8: dispatched (BASE 4bd1eb9)
Task 8: implementer af30d8276a27e701c (sonnet)
Task 8: implementer DONE_WITH_CONCERNS (abf1223): badge variants moved to lead-format; zodOptions imported from admin/site/site-form; LEVEL_LABELS duplicated; convert dialog stays mounted after converted.
Ruling: family name prefill stays `Семья {child_name}` (e.g. «Семья Маша») — automatic Russian genitive is unreliable and the field is editable — cost if wrong: tutor edits the name by hand.
Task 8: review dispatched (afd9ffa7168ad765f, sonnet) on 4bd1eb9..abf1223
Task 8: review Approved. ⚠️ 401/403 via shared query-client handler (plan 2); just-wrapper runs & browser → Task 9.
Task 8: minor (deferred): zodOptions imported from route file app/admin/site/site-form (3 copies overall) — move to lib
Task 8: minor (deferred): LEVEL_LABELS duplicated from child-form-dialog
Task 8: minor (deferred): convert 409 doesn't refresh lead (stale status)
Task 8: minor (deferred): history key changed_at-to_status may collide; dialog title flicker on close; tutor_comment draft not refreshed
Task 8: complete (commits 4bd1eb9..abf1223, review clean)
Task 9: dispatched (BASE abf1223) — implementer: docs + compose web SMARTCAPTCHA_CLIENT_KEY + README note drop "$" group + steps 1,2,4; controller: walkthrough
Task 9: implementer a69ed783a95cf6a1f (sonnet)
Task 9: implementer DONE (f9d032c, 20600e2): compose web SMARTCAPTCHA_CLIENT_KEY, .env.example, README «Заявки и уведомления» + XGROUP DESTROY ops note; backend 520 / 99.10%, frontend 280; build OK (/ ◐, /admin/leads ○, /admin/leads/[id] ◐).
Task 9: controller walkthrough (dev stack, built-in browser):
  1 375px: #trial form, phone mask 89991234567 → +7 (999) 123-45-67, no h-scroll, consent required («Необходимо согласие…»), submit → «Спасибо!»; UTM test/walkthrough stored in lead — OK
  2 worker notify_new_lead: same request_id as POST /api/public/leads, telegram_disabled, task_finished is_err=False — OK
  3 rate limit: 3 leads/hour then 429 rate_limited Retry-After 3576 — OK
  4 /admin/leads list, card; «Отказ» without reason blocked; «Связались» + comment in history — OK
  5 trial_scheduled via SQL → convert: prefill (Семья Петя, child, parent, +7 phone), invitation link + «Открыть семью»; /invite prefilled ФИО + phone — OK
  Consumer group lag 0 on dev Redis — no XGROUP DESTROY needed here.
  BUG (for final fix wave): messenger_handle stored with leading "@" ("@olga_test") → Telegram text "Telegram @@olga_test"; normalize handle on input (strip @, t.me/ prefixes) like ContactsBlock telegram.
  Note: DisabledNotifier path still sets notified_at although nothing was sent.
Task 9: review Needs fixes — Important: README says restart reloads .env (it does not); client key location for `just web` (frontend/.env.development) undocumented; minors folded in. Fix round 1/5 dispatched to a69ed783a95cf6a1f
Task 9: fix (db55481) — README recreate vs restart, client key in frontend/.env.development, key pairing, prod validator wording; retry wording disputed ("5 attempts total"). Re-review dispatched (a332759090225d101, haiku) on 20600e2..db55481
Task 9: fix round 1/5 (4 addressed, 0 open — restart vs recreate, client key location/pairing, prod list, retry wording verified 5 attempts total; commits 20600e2..db55481)
Task 9: minor (deferred): README "restart only after code changes" — qualify as dev-stack (bind mount only in dev)
Task 9: complete (commits abf1223..db55481, review clean)
Final review: dispatching (opus) on 8c54300..db55481
Final review: dispatched (a9fecc6e457e961cf, opus) on 8c54300..db55481
Final review: With fixes. Critical: bot token logged by httpx INFO on every send. Important: "@@" handle; Telegram content beyond spec/privacy; limiter Redis-down loses lead (README claims otherwise); captcha hang + real-key path unverified. Minor: list stale after status change, phone search "8…", disabled notifier sets notified_at, PATCH comment w/o status, deprecated disable_web_page_preview, README dev-stack wording.
Ruling: Telegram message trimmed to spec 4.5 п.1 — parent name, child age, contact method with its contact value (phone or @handle), admin link; child name, goal, preferred time removed. Privacy policy additionally states Yandex SmartCaptcha (token + IP) and IP processing for anti-spam — spec is binding, policy must match what is sent — cost if wrong: tutor opens the admin link for details.
Ruling: lead rate limiter fails open when Redis is unavailable (warning lead_rate_limit_unavailable; honeypot and captcha still apply) — spec 4.5/6.5 «заявка сохранена независимо», README already promises it — cost if wrong: while Redis is down there is no per-IP limit.
Ruling: DisabledNotifier path leaves notified_at NULL and logs lead_notification_skipped — notified_at must mean "delivered" — cost if wrong: none (dev only).
Ruling: PATCH with comment but no status → 422 on comment — silent drop is surprising — cost if wrong: one more validation rule.
Ruling: carried into plan 7 scope — uvicorn --proxy-headers/--forwarded-allow-ips (+ test real client IP), PUBLIC_BASE_URL prod check, real-key SmartCaptcha smoke on prod domain, httpx log level in Sentry config — cost if wrong: site-wide 3/hour limit behind nginx until plan 7.
Final fix wave: dispatched (BASE db55481)
Final fix wave: implementer a79e340f5eb1d1dd5 (sonnet), brief final-fix-brief.md (11 items)
Final fix wave: implementer DONE (db8b27f, 14e6cc9, 4c999bf); backend 544 / 99.07%, frontend 296. Amended own unpushed commit once (trailer typo).
Ruling: revert "onChallengeHidden clears pending" from item 5 — real widget may emit hidden before success, clearing would drop leads; watchdog already prevents hangs — cost if wrong: a stale pending survives until next submit (harmless, overwritten).
Final fix wave: revert commit 12f7feb (hidden keeps pending; hidden→success test). Scoped re-review dispatched (a4af656480c269bee, sonnet) on db55481..12f7feb
Final fix wave: re-review — all 11 items ADDRESSED (+ revert ruling honoured), no new Critical/Important (commits db55481..12f7feb).
Final: minor (deferred): messenger_handle max_length=64 checked before strip — long pasted t.me link → 422
Final: minor (deferred): legacy leads with leading "@" not migrated (graceful fallback); "@@x" strips one "@"
Final: minor (deferred): leads stored while Telegram disabled are never re-sent once configured
Final review: complete — merge-ready.
