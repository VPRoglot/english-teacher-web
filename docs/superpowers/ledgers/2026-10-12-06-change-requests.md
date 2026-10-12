# SDD ledger — plan: docs/superpowers/plans/2026-10-12-06-change-requests.md

BASE (branch start): 4bf164a (branch worktree-requests)
Spec: docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md
Context files: global.md, env-notes.md, implementer-contract.md, reviewer-contract.md (this dir)

## Pre-flight scan

| Пара / задача | Производит → потребляет | Результат |
|---|---|---|
| T1 ↔ T2/T4/T5 | ChangeRequest model, lesson_ids_with_requests, archive rule with requests → create/approve/archive_child_series | согласовано |
| T1 ↔ T9 | AdminLessonDetail.has_requests → кнопка «Удалить» | согласовано |
| T2 ↔ T3 | NOTIFY_CHANGE_REQUEST_TASK, kwargs request_id: str → задача | согласовано |
| T2 ↔ T4 | is_late_cancel, ChangeRequestNotPending/NotFound errors, ChangeRequestType/Status | согласовано |
| T2 ↔ T7 | useCreateChangeRequest/useWithdrawChangeRequest, LessonForFamilyDetail.change_request | согласовано |
| T4 ↔ T6 | list_admin_requests → pending_summary, ChangeRequestAdminItem | согласовано |
| T4 ↔ T8 | useListChangeRequests/useApproveChangeRequest/useRejectChangeRequest | согласовано |
| T6 ↔ T9 | useGetDashboard, DashboardResponse | согласовано |
| T5 ↔ T9 | архив завершает серии → текст подтверждения | согласовано |
| T8 ↔ (план 5) | useTutorTimeZoneStatus, LessonTimeFields, invalidateSchedule | существуют в main (fix wave плана 5) |
| T1 self | защита в reconcile ↔ правило R4 «сохраняемое» | согласовано |
| T2 self | create блокирует занятие; withdraw — только запрос; T4 approve — занятие → запрос: циклов нет | согласовано |
| T3 self | политика конфиденциальности — frontend-файл в backend-задаче | Ruling 1 |
| T4 self | порядок блокировок уточнён в плане | согласовано |
| T6 self | list_leads(status=NEW, limit=5) — сигнатура из плана 4 | согласовано |
| T10 self | шаг 3 — контроллер | Ruling 2 |

Ruling 1: Task 3 also edits frontend privacy-policy.tsx and its test (one line of copy tied to the new Telegram message) — keeps the policy in the same commit as the data flow it describes — cost if wrong: none.
Ruling 2: Task 10 step 3 (browser walkthrough) is done by the controller on an isolated compose project; the implementer does steps 1, 2 (without just down — controller stops stacks), 4 — cost if wrong: none.

## Tasks
Task 1: dispatched (implementer a53311b0d521054a5, sonnet; BASE 4bf164a)
Task 1: implementer DONE (099eaa8): model, 0006, guards, has_requests, factory; backend 840/99.26%; process: model before tests. Review dispatched (abcc126ef5c29a059, sonnet) on 4bf164a..099eaa8
Task 1: review Approved.
Task 1: minor (deferred): TDD order deviation (model before tests); weak no-twin assertions in guard tests; _exists typing; guards tested only with rejected request
Note for plan 7: RESTRICT FKs on change_requests → purge-family must delete change_requests before lessons/children/users
Task 1: complete (commits 4bf164a..099eaa8, review clean)
Task 2: dispatched (BASE 099eaa8)
Task 2: implementer ae6f6082e08875fa0 (sonnet)
Task 2: implementer DONE_WITH_CONCERNS (5e03d82): created_at from injected now; function-local imports for cycles; withdraw locks lesson→request; race fallback untested concurrently; hooks useCreateChangeRequest/useWithdrawChangeRequest; backend 867/99.14%. Review dispatched (a0ed5a2a52dccda74, opus)
Task 2: review Approved (opus).
Task 2: minor (deferred): child view of change_request untested; function-local imports of private _lock_lesson (move to shared lower module); cabinet_router imports Now from admin_router (move get_now to core); enqueue-after-commit only by inspection; comment vs proposed_text strip location; no concurrent index-fallback test
Task 2: complete (commits 099eaa8..5e03d82, review clean)
Task 3: dispatched (BASE 5e03d82)
Task 3: implementer a79b5acad8659afc2 (sonnet)
Task 3: implementer DONE (adfa5e4): notify_change_request + privacy line; backend 877/99.07%; no_child skip untested. Review dispatched (ae439f42d22782639, sonnet)
Task 3: review Approved.
Task 3: minor (deferred): no_child skip silent/untested; check order notified→pending; param named type
Task 3: complete (commits 5e03d82..adfa5e4, review clean)
Task 4: dispatched (BASE adfa5e4)
Task 4: implementer aefcae736b3da1e7d (sonnet)
Task 4: implementer DONE (92530ad): list/approve/reject; settings read unlocked in approve; hooks useListChangeRequests/useApproveChangeRequest/useRejectChangeRequest; backend 894/99.03%. Review dispatched (afa48d08c7279fcf2, opus)
Task 4: review Needs fixes (opus) — Important [plan-mandated RF1]: no approve-vs-withdraw evidence (lock-order sql_log test + approve-then-withdraw 409). Minors: endpoint late boundaries (added to fix), is_late of resolved requests recomputed with current policy, weak requested_by_name assert, no reject length test, needless populate_existing.
Task 4: fix round 1 dispatched to aefcae736b3da1e7d
Task 4: fix round 1/5 (2 addressed, 0 open — lock-order + withdraw-after-approve tests, endpoint late boundaries; commits 92530ad..041e801)
Task 4: minor (deferred): is_late of resolved requests recomputed with current policy; weak requested_by_name assert; no reject length test; needless populate_existing in list
Task 4: complete (commits adfa5e4..041e801, review clean)
Task 5: dispatched (BASE 041e801)
Task 5: implementer a09a4a140fa80c095 (sonnet)
Task 5: implementer DONE (5d81d8d): hook in families admin_router, list_child_ids, was-active pre-read; backend 905/98.98%. Review dispatched (a4bc2670e2649ff9a, sonnet)
Task 5: review Approved.
Task 5: minor (deferred): was_active guard not exercised by a failing-without-it test (archived child can't get new series anyway); misleading test name; duplicate get_child pre-read; Redis sessions deleted before possible rollback (pre-existing order); families router imports Now from lessons router
Task 5: complete (commits 041e801..5d81d8d, review clean)
Task 6: dispatched (BASE 5d81d8d)
Task 6: implementer a45c3293e6c468b84 (sonnet)
Task 6: implementer DONE (564a51d): dashboard module, useGetDashboard; needs_marking includes trials; backend 910/99.02%. Review dispatched (a6d8350bc836ff2d9, sonnet)
Task 6: review Approved.
Task 6: minor (deferred): duplicated admin item comprehension in pending_summary/list_admin_requests; tests lack anonymized lead, trial, exact-now/day_end edge cases
Task 6: complete (commits 5d81d8d..564a51d, review clean)
Task 7: dispatched (BASE 564a51d)
Task 7: implementer aed61e0f708078047 (sonnet)
Task 7: implementer DONE (d215380): request block + dialog + format lib, invalidate-my-lessons helper; FE 516. Review dispatched (a90fa78889b386d40, sonnet)
Task 7: review Approved.
Task 7: minor (→ final fix wave, spec 4.5 «заранее предупреждает»): late warning absent and submit enabled while schedule settings loading/failed — disable submit until settings loaded, show error on failure
Task 7: minor (deferred): no tests for invalidation, 422, withdraw 409; minute-rounded now boundary; import order; untested «Комментарий репетитора» line
Task 7: complete (commits 564a51d..d215380, review clean)
Task 8: dispatched (BASE d215380)
Task 8: implementer a88d94065aa648954 (sonnet)
Task 8: implementer hit session limit (uncommitted work in tree); resumed same agent
Task 8: implementer DONE (6dcbdac): queue page, dialogs, nav, predicate extended; withDuration prop on LessonTimeFields; partial TDD order; FE 527. Review dispatched (a8aefac54c7f1cabf, sonnet)
Task 8: review Approved.
Task 8: minor (deferred): incomplete ARIA tabs; duplicated submit button; reject over-invalidates schedule; approve reschedule prefilled with current time allows no-op approve (consider guard); stale request after 409; long comment in lesson-mutations
Task 8: complete (commits d215380..6dcbdac, review clean)
Task 9: dispatched (BASE 6dcbdac)
Task 9: implementer a2c7cefd857685d94 (sonnet)
Task 9: implementer DONE (7ce8d01): dashboard, has_requests hint, archive confirms (new ConfirmDialog for child archive); FE 532. Review dispatched (a51de3296af74662a, sonnet)
Task 9: review Approved.
Task 9: minor (deferred): request rows link only to queue; no plural/caps asserts; family archive confirm not clicked in test; plain error state
Task 9: complete (commits 6dcbdac..7ce8d01, review clean)
Task 10: dispatched (BASE 7ce8d01) — implementer: README + steps 1, 2 (no just down), 4; controller: walkthrough (Ruling 2)
Task 10: implementer a6a53863f357fba52 (sonnet)
Task 10: review Needs fixes — Important: README says telegram_disabled logged on request path (it isn't). Fix round 1 dispatched to a6a53863f357fba52.
Walkthrough note (→ final fix wave): notify_change_request logs change request id under key request_id, clobbering the trace request_id in structlog context — rename to change_request_id
Task 10: fix round 1/5 (2 addressed, 0 open — README log event, dashboard row links; commits b0287f8..d6d7d71)
Task 10: complete (commits 7ce8d01..d6d7d71, review clean)
Walkthrough (controller, isolated stack requests-walk, removed after):
  1 parent 375px: «Запросить отмену» 10 h before with policy 24 → late warning; request sent, «Ждёт ответа репетитора», «Поздняя отмена», only «Отозвать запрос» — OK
  2 worker notify_change_request → change_request_notification_skipped reason=disabled, is_err=False — OK (log key bug noted)
  3 tutor dashboard: new lead 1, pending 2, needs marking 1, today 1; 375px no h-scroll — OK; queue approve late cancel → lesson cancelled_late, «Запрос одобрен» — OK
  4 approve reschedule 15.10 17:30 MSK → starts_at 14:30Z, queue empty — OK
  5 reject without response blocked («Напишите ответ родителю»), with response → «Запрос отклонён»; parent sees status rejected + tutor_response — OK
  6 withdraw → «Отозван», request buttons back — OK
  7 child: sees request, no buttons, POST → 404 — OK
  8 archive child → active series 0, 16 future series lessons deleted, one-off lessons (with requests) kept — OK
  Cleanup: viewport reset, dev server + orphan node stopped, requests-walk down -v
Final review: dispatched (aebd6e46f89ef2562, opus) on 4bf164a..d6d7d71
Final review: With fixes (opus). Important: «Все» tab shows only pending (backend default pending); log key request_id clobbers trace id (tasks.py + requests_service.py); late warning missing while settings load/fail. Minors: archive vs concurrent request 500, archive stale caches, dashboard after lead actions, is_late recomputed, 200 cap, lock held during send, real clock in cabinet request tests.
Ruling: fix wave = Important 1–3 + Minors archive-lock, archive cache, dashboard-after-leads, real-clock tests, no-op reschedule approve 422; is_late-of-resolved, 200 cap, lock-during-send, declined list deferred/accepted — cost if wrong: small UI inconsistencies remain until plan 7.
Final fix wave: dispatched (BASE d6d7d71), brief final-fix-brief.md (8 items)
Final fix wave: implementer a76a0a51de88b9f40 (sonnet)
Final fix wave: implementer DONE (1529086 033886a 1fee9ed): all 8 items; backend 914/99.05%, FE 535; no RED for FE no-op field error. Re-review dispatched (ac1686417330c5215, opus) on d6d7d71..1fee9ed
Final fix wave: re-review — all 8 ADDRESSED, no new Critical/Important (commits d6d7d71..1fee9ed).
Final: minor (deferred): unfiltered list ties pending by id desc vs asc in pending tab; invalidateSchedule not awaited in family pages
Final review: complete — merge-ready (controller verified: backend 914/99.05%, FE 535, lint clean).
