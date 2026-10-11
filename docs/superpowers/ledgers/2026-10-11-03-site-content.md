# SDD ledger — plan: docs/superpowers/plans/2026-10-11-03-site-content.md

BASE (branch start): e504f7e (branch worktree-site-content)
Spec: docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md
Context file for subagents: .superpowers/sdd/2026-10-11-03-site-content/global.md (уточнения, Global Constraints, Review Focus, структура файлов)

## Pre-flight scan

| Пара / задача | Производит → потребляет | Результат |
|---|---|---|
| T1 ↔ T3 | обязательные поля Settings (revalidate_secret; s3_*) → все места, создающие Settings вручную | Конфликт-риск: `app/cli.py export_openapi` создаёт Settings-заглушку; tests/core/test_config.py, test_ready.py. См. Ruling 1 |
| T1 ↔ T4 | TaskQueueDep, FakeTaskQueue, REVALIDATE_SITE_TASK → обработчики PUT и тесты | согласовано |
| T1 ↔ T10 | worker в compose, `just restart` → ручная проверка | согласовано |
| T2 ↔ T3/T4 | Media, BLOCK_SCHEMAS, referenced_media_ids, BlockKey → upload/save_block | согласовано |
| T3 ↔ T4 | MediaOut, media_url, tutor_client/parent_client фикстуры → T4 тесты | согласовано |
| T4 ↔ T5 | `GetPublicSiteResponse` в `zod/public/public.ts` → getSite | согласовано (зависит от tag "public") |
| T4 ↔ T8/T9 | useGetSiteBlocks, getGetSiteBlocksQueryKey, useUpdate*Block, Update*BlockBody, useUploadMedia → редакторы | согласовано (имена orval из operationId) |
| T5 ↔ T6/T7 | siteFixture → тесты лендинга/SEO | T6 тест ждёт «30 мин · Онлайн» и «Бесплатно», T5 не фиксирует длительность бесплатной услуги. См. Ruling 2 |
| T6 ↔ T7 | contactLinks labels → PrivacyPolicy тест `link name "anna@example.com"` | T6 не фиксирует label email/phone. См. Ruling 3 |
| T6 ↔ T7 | page.tsx (LandingContent) → generateMetadata + JSON-LD | согласовано, T7 правит тот же файл |
| T8 ↔ T9 | PhotoField, SiteEditor, общее поведение редактора → списочные редакторы | согласовано |
| T1 self | тесты test_config ↔ Settings | согласовано |
| T2 self | тесты ↔ таблица полей; миграция без app.* ↔ тест заглушек | согласовано |
| T3 self | тест upload: имя файла photo.png с JPEG-содержимым → ответ .jpg | согласовано (тип по содержимому) |
| T4 self | тест порядка commit→enqueue ↔ `_save_and_revalidate` | согласовано |
| T5 self | route 401 для "dev-revalidate-secret-change-me" без Bearer | согласовано |
| T6 self | `section[id]` порядок без hero ↔ hero без id | согласовано (hero-секция без id) |
| T7 self | robots/sitemap async + connection ↔ тесты с моком next/server | согласовано |
| T8 self | FormData тест может сразу пройти | допустимо, план это оговаривает |
| T9 self | вложенные loc → Alert ↔ T4 message | согласовано |
| T10 self | только docs + ручная проверка | согласовано |

Ruling 1: Все места, создающие Settings вручную (cli.export_openapi, тесты), получают значения-заглушки для новых обязательных полей (revalidate_secret, s3_*) — export-openapi должен работать без .env и секретов (CI gen-api) — если неверно: CI/`just gen-api` падают, заметно сразу.
Ruling 2: В siteFixture бесплатная услуга — `duration_min: 30`, `format: "Онлайн"`, `price_rub: 0`; платная — 60 мин, 1500 ₽ — фиксирует ожидания теста T6 — если неверно: правка фикстуры.
Ruling 3: contactLinks: label telegram `@{username}`, whatsapp «WhatsApp», phone — сам номер (`+79991234567`), email — сам адрес — нужно тесту T7 и понятно пользователю — если неверно: косметика.

## Tasks
Task 1: dispatched (implementer a8414674220d88060, sonnet; BASE e504f7e)
Task 1: implementer DONE_WITH_CONCERNS (e2eb107). Concerns: retries without pause (RedisStreamBroker ignores delay label); default_retry_label=True added; test_sessions made type-aware; guarded broker startup (5s timeout).
Ruling: retry pause is implemented in-worker — subclass SmartRetryMiddleware that awaits asyncio.sleep(delay) before re-sending (delay exponential with jitter, cap 60 s) instead of a taskiq scheduler process — spec 4.5/6.5 require growing pause; no extra container — cost if wrong: a sleeping retry holds one async slot of the worker (max_async_tasks is large; tasks are rare).
Ruling: default_retry_label=True accepted (deviation from brief) — tasks are enqueued by name so task-level labels never reach the message — cost if wrong: every task retries by default (all our tasks are idempotent per spec 6.5).
Task 1: fix (pre-review, ruling) fc08bbf DelayedRetryMiddleware; review dispatched (a7ac09b28c1a1d67c, sonnet) on e504f7e..fc08bbf
Task 1: review Approved (no Critical/Important). ⚠️ resolved: X-Request-ID in real worker — verify in Task 10 walkthrough (worker logs share request_id); Redis-down startup — covered by existing test_ready_reports_redis_down, full suite green (271).
Task 1: minor (deferred): middleware sets private _request_id ContextVar — add public set/clear helpers
Task 1: minor (deferred): no dedicated test for broker_startup_failed branch in lifespan
Task 1: minor (deferred): DelayedRetryMiddleware docstring — message unacked during pause; restart delays retry until stream reclaim
Task 1: minor (deferred): retry test depends on upstream make_delay curve (strictly increasing, last == 60)
Task 1: minor (deferred): default_retry_label=True retries all tasks — add idempotency reminder comment; retry labels in register_tasks redundant
Task 1: minor (deferred): consumer group created at startup; enqueue during Redis-down window could be skipped (narrow)
Task 1: complete (commits e504f7e..fc08bbf, review clean)
Task 2: dispatched (implementer a7b8094f8a6e0dc39, sonnet; BASE fc08bbf)
Task 2: implementer DONE (948b7dc); BlockKey lives in models.py; migration hand-written. Review dispatched (a94c6b4d83f9041a8, sonnet) on fc08bbf..948b7dc
Task 2: review Approved. ⚠️ (test results, alembic.ini untouched) — accepted from report; full suite re-runs in later tasks.
Task 2: minor (deferred): phone/telegram regexes accept non-ASCII digits (\d) — use re.ASCII / [0-9]
Task 2: minor (deferred): telegram URL prefixes case-sensitive
Task 2: minor (deferred): FaqItem.answer reuses ReviewText alias — rename to neutral LongText
Task 2: complete (commits fc08bbf..948b7dc, review clean)
Task 3: dispatched (BASE 948b7dc)
Task 3: implementer ac806cef7f4944f57 (sonnet)
Task 3: implementer DONE_WITH_CONCERNS (84d7eb3). Concerns: minio/minio & minio/mc not pullable → Chainguard images; test_cli env helper; split auth test; multidict downgraded 7.1→6.9.1; Starlette buffers full multipart before 5 MB check.
Ruling: dev/test MinIO uses cgr.dev/chainguard/minio:latest and cgr.dev/chainguard/minio-client:latest-dev instead of minio/minio, minio/mc — official images are not pullable here; dev/test only (prod uses provider S3) — cost if wrong: unpinned latest may break dev/test on upstream change; pin by digest later.
Ruling: request body size limit stays at nginx (client_max_body_size 6m, plan 7) — app check after Starlette buffering is the second line — cost if wrong: before plan 7, large uploads by the (authenticated) tutor are buffered to disk.
Task 3: review dispatched (a697055137c0fb5a6, sonnet) on 948b7dc..84d7eb3
Task 3: review Needs fixes — Important: MPO (multi-frame JPEG from phones) rejected with 415. ⚠️ resolved: base compose passes S3_* via env_file ../.env (x-backend anchor); dev stack check per report.
Task 3: minor (deferred): warnings.catch_warnings in process_image is not thread-safe under to_thread — use Image.MAX_IMAGE_PIXELS + DecompressionBombError
Task 3: minor (deferred): plan 7 nginx client_max_body_size slightly above 5 MB (6m per spec)
Task 3: minor (deferred): Chainguard images unpinned :latest, minio without healthcheck — pin digest
Task 3: minor (deferred): EXIF stripping tested only for JPEG — parametrize PNG/WebP/XMP
Task 3: minor (deferred): test_media_api asserts Media row via identity map
Task 3: fix round 1/5 dispatched to ac806cef7f4944f57 (MPO)
Task 3: fix round 1/5 (1 addressed, 0 open — MPO accepted as JPEG; commits 84d7eb3..024f865)
Task 3: minor (deferred): MPO test doesn't assert first frame kept / no EXIF-oriented MPO case
Task 3: complete (commits 948b7dc..024f865, review clean)
Task 4: dispatched (BASE 024f865)
Task 4: implementer a4027f3f562729b39 (sonnet)
Task 4: implementer DONE (bcbc352). Generated names: useGetSiteBlocks, useUpdate{Hero|About|Services|Reviews|Faq|Contacts}Block, getPublicSite; zod/public/public.ts GetPublicSiteResponse; zod/admin/admin.ts Update*BlockBody. Note for T8: UpdateContactsBlockBody has min(1)/email — form must turn "" into null before zod.
Task 4: review dispatched (a8e5bd13132eef57d, sonnet) on 024f865..bcbc352
Task 4: review Approved. ⚠️ resolved: generated names verified by grep (GetPublicSiteResponse, UpdateHeroBlockBody, useUploadMedia, getGetSiteBlocksQueryKey, useUpdateHeroBlock); shared db_session confirmed by passing order test.
Task 4: minor (deferred): request_site_revalidation has no timeout — hanging Redis blocks PUT (block already committed) — wrap in asyncio.timeout
Task 4: minor (deferred): unknown-photo 422 tested only for reviews/single id — add hero/about and multiple ids
Task 4: minor (deferred): media row could vanish between check and upsert (no FK in JSONB) — public read degrades to photo None
Task 4: complete (commits 024f865..bcbc352, review clean)
Task 5: dispatched (BASE bcbc352)
Task 5: implementer ab1e9c59300591384 (sonnet)
Task 5: implementer DONE (dfb3b6b); route reads REVALIDATE_SECRET directly (503 instead of throw). Review dispatched (af29080b12f37cebb, sonnet) on bcbc352..dfb3b6b
Task 5: review Approved. ⚠️ 'use cache' runtime behaviour / build without API — verify in Task 6/7 build steps and Task 10 walkthrough.
Task 5: minor (deferred): unexpected-shape test uses bare toThrow — assert ZodError
Task 5: minor (deferred): Accept header and 5 s signal not asserted in getSite test
Task 5: minor (deferred): env_file ../.env hands all backend secrets to web — narrow later
Task 5: minor (deferred): API_PROXY_URL and API_INTERNAL_URL duplicate in dev
Note for T7: SITE_URL missing from .env.example and compose web env — T7 must add it.
Task 5: complete (commits bcbc352..dfb3b6b, review clean)
Task 6: dispatched (BASE dfb3b6b)
Task 6: implementer ab8ab6526d83c768b (sonnet)
Task 6: implementer DONE_WITH_CONCERNS (5e04921): error.tsx uses retry (Next 16.4), hero without own CTA, 375px not browser-checked; build shows / as Partial Prerender.
Ruling: CTA only in header (no duplicate hero button) — spec 5.1 names the header button; plan test expects a single CTA link — cost if wrong: slightly weaker hero conversion, easy to add later.
Task 6: review dispatched (abf4424ffeb800352, sonnet) on dfb3b6b..5e04921
Task 6: review Approved. ⚠️ 375px — verify in Task 10 walkthrough; build claim — re-run in Task 7/10.
Task 6: minor (deferred): next/image `priority` deprecated in Next 16 → `preload`
Task 6: minor (deferred): error.tsx doesn't log error
Task 6: minor (deferred): no tests for error.tsx/page.tsx
Task 6: minor (deferred): markdown allows external <img> — consider disallowedElements img
Task 6: complete (commits dfb3b6b..5e04921, review clean)
Task 7: dispatched (BASE 5e04921)
Task 7: implementer a4d75f4085919a7e8 (sonnet)
Task 7: implementer DONE_WITH_CONCERNS (6f130e4): relative canonical on /privacy; noindex already present (no follow:false); SiteHeader homeHref; SITE_URL in .env.example. Review dispatched (a68f428b00eda1bc2, sonnet) on 5e04921..6f130e4
Task 7: review Approved but spec ❌ (Missing follow:false on 5 noindex files) → fix round. ⚠️ resolved: #top (landing main) and #trial exist; notification text vs policy — check in plan 4 (Telegram task must send only name, child age, contact method).
Task 7: minor (deferred): privacy test getAllByText(/Telegram/) weaker than brief
Task 7: fix round 1/5 dispatched (follow:false, absolute canonical on /privacy, SiteHeader homeHref test)
Task 7: fix round 1/5 (3 addressed, 0 open — follow:false, absolute /privacy canonical, header test; commits 6f130e4..87bd3d2)
Task 7: minor (deferred): /privacy generateMetadata has no unit test (runtime-checked only)
Task 7: complete (commits 5e04921..87bd3d2, review clean)
Task 8: dispatched (BASE 87bd3d2)
Task 8: implementer a4c3181430eeb7e63 (sonnet)
Task 8: implementer a4c3181430eeb7e63 STOPPED by user before reporting (BASE 87bd3d2); check git status/log before resuming
Task 8: re-dispatched after user resume (implementer aa85c05e9ca52c59a, sonnet; BASE 87bd3d2)
Task 8: implementer DONE (1c52c55): extra site-form.tsx (BlockForm/TextField/useAfterSave/zodOptions), transform().pipe() blank->null. Review dispatched (a53e86f860b57d08c, sonnet) on 87bd3d2..1c52c55
Task 8: review Approved. ⚠️ resolved: Toaster mounted in root layout; credential 422 falls back to Alert (accepted deviation); backend strips/caps credentials (Task 2 schema 1..200, ≤20).
Task 8: minor (deferred): about credentials — blank rows filtered before validation, so error index points at wrong row
Task 8: minor (deferred): about preview unmounts textarea, Label htmlFor dangling
Task 8: minor (deferred): PhotoField error not cleared by «Убрать фото»
Task 8: minor (deferred): whitespace-only hero title/name passes client min(1) (server 422 catches; untested)
Task 8: complete (commits 87bd3d2..1c52c55, review clean)
Task 9: dispatched (BASE 1c52c55)
Task 9: implementer ac73b6699602929d7 (sonnet)
Task 9: implementer DONE_WITH_CONCERNS (d1dd73c): ListControls noun prop, child_age setValueAs, TextareaField + number messages in site-form. Review dispatched (ab2f11de5499e3483, sonnet) on 1c52c55..d1dd73c
Task 9: review Approved. ⚠️ resolved: backend 422 message pinned by Task 4 test (test_unknown_photo...); responsive — Task 10 walkthrough.
Task 9: minor (deferred): unknown-photo Alert doesn't name the review; could setError on items.N.photo_media_id from loc
Task 9: minor (deferred): fractional numbers show «Введите число» — add step=1 / «целое число»
Task 9: minor (deferred): about-editor not using shared TextareaField
Task 9: minor (deferred): no remove/reorder tests beyond one move for reviews/FAQ; no 422 test for services/FAQ
Task 9: complete (commits 1c52c55..d1dd73c, review clean)
Ruling: Task 10 split — implementer does docs + full lint/test + build-without-API (steps 1,2,4); controller runs the browser walkthrough (step 3) since the built-in browser lives in the controller session; bugs found go to a fix dispatch — cost if wrong: none beyond who presses the buttons.
Task 10: dispatched (BASE d1dd73c)
Task 10: implementer ac268f5d47a5b3668 (sonnet) — docs + checks; walkthrough by controller after
Task 10: implementer DONE (d21aa2c): README section, .env.example (+REVALIDATE_URL, S3_REGION commented), frontend/README rewritten; lint/test green (backend 362, 99.04%; frontend 202); build w/o API OK (/ and /privacy ◐, robots/sitemap/api/revalidate ƒ, /admin/site ○).
Task 10: controller walkthrough (built-in browser, dev stack):
  1 stubs on /, JSON-LD Person+Service, canonical, og:title, robots.txt (6 disallows + sitemap), sitemap.xml — OK
  2 /admin/site: edited hero name/title, uploaded JPEG (canvas) → /media/site/<uuid>.jpg 200 image/jpeg; toast; landing updated within ~1 s; api and worker share request_id; POST /api/revalidate 204 — OK
  3 reviews added, FAQ emptied (section+nav hidden), contacts normalized (8 (999)… → tel:+79991234567, @anna_english → t.me), about markdown: <strong> kept, no <script>, no javascript: links — OK
  4 Next stopped → retries 5.34 s, 10.72 s, 32.98 s, success on attempt 4 after Next restart — OK (log order: failed attempt's task_finished is printed after the pause — cosmetic)
  5 /privacy: h1, operator name from hero, 12 месяцев, Telegram, mailto, absolute canonical — OK
  6 375 px: scrollWidth 375 (no horizontal scroll), header CTA → #trial — OK
  Note: curl from Git Bash sent Cyrillic as '?' (client encoding, not app) — re-saved via browser.
Task 10: minor (deferred): DelayedRetryMiddleware sleeps inside on_error, so task_finished of the failed attempt logs after the pause (confusing log order)
Task 10: review Approved (docs facts traced to code).
Task 10: minor (deferred): README says all vars in .env.example (frontend vars live in frontend/.env.development)
Task 10: minor (deferred): frontend/README "run from repo root" wrong for bare pnpm
Task 10: minor (deferred): "Next reads env at request time" imprecise for API_PROXY_URL/MEDIA_PROXY_URL (rewrites)
Task 10: minor (deferred): .env.example:29 long comment line
Task 10: complete (commits d1dd73c..d21aa2c, review clean)
Final review: dispatching (opus) on e504f7e..d21aa2c
Final review: dispatched (a1f61688f8709b16f, opus) on e504f7e..d21aa2c
Final review: With fixes. Important: (1) bare 10-digit RU mobile "999 123-45-67" → "+9991234567"; (2) body-size ruling understated — FastAPI parses multipart before auth, unauthenticated clients can spool unbounded body; (3) web container gets all backend secrets via env_file.
Ruling (correction of Task 3 body-limit ruling): cost is unauthenticated disk spooling, not tutor-only — add an app-level ASGI guard for /api/admin/media now (Content-Length + streamed bytes cap) and keep nginx client_max_body_size 6m as a hard plan 7 item — cost if wrong: small middleware to maintain.
Ruling: fix wave includes Important 1–3 plus cheap minors (priority→preload, privacy text contradiction + fallback, markdown img disallowed + h1/h2→h3, duplicate credential keys, log zod parse failure in getSite) — cost if wrong: slightly larger fix diff.
Ruling: deferred to plan 4 Task 1 — broker/enqueue timeouts, consumer group consumer_id="0", stream maxlen, Telegram task idempotency + default_retry_label reminder; deferred to plan 7 — nginx 6m, Chainguard digest pinning, CSP for JSON-LD — cost if wrong: those risks persist until those plans (no prod before plan 7).
Final fix wave: dispatched (BASE d21aa2c)
Final fix wave: implementer a9c091cce1b6a99b5 (sonnet), brief final-fix-brief.md
Final fix wave: implementer DONE (fd64733, f3237e2, 60dc2a8); backend 379 / 98.97%, frontend 206; build OK. Scoped re-review dispatched (a665e75083d56527d, sonnet) on d21aa2c..60dc2a8
Final fix wave: re-review — all 8 items ADDRESSED, no new Critical/Important (commits d21aa2c..60dc2a8).
Final: minor (deferred): compose ${SITE_URL}/${REVALIDATE_SECRET} without :? guard — stale .env renders empty
Final: minor (deferred): upload_limit second receive after exceed and unrelated-exception re-raise not covered by tests
Final review: complete — merge-ready.
