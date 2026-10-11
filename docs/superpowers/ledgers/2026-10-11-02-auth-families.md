# SDD ledger — plan: docs/superpowers/plans/2026-10-11-02-auth-families.md
Spec: docs/superpowers/specs/2026-10-11-english-tutor-mvp-design.md
Executor: subagent-driven (controller = main session). Branch worktree-auth-families from fa85bdb. Baseline: 61 backend + 7 frontend tests green.

## Pre-flight: shared interfaces
| Consumer <- Producer | Interface | Finding |
|---|---|---|
| T6-T10 <- T1 | API_ERROR_RESPONSES on every router; operationId = route.name | consistent; route function names must be unique (listed in T7-T10) |
| T8, T9 <- T2 | validate_password, CHILD_PASSWORD_MIN_LENGTH | consistent |
| T7-T10 <- T3 | models + tests/factories.py | T7 adds login() to factories but T7 Files omits it → Ruling R1 |
| T5 <- T4 | `redis` fixture + FLUSHDB in app fixture | consistent |
| T7-T9 <- T4 | SessionStore, SessionStoreDep, set/clear_session_cookie | consistent |
| T8 <- T4 | tokens.sha256_hex (T4 creates, T8 extends) | consistent (fixed in plan self-review) |
| T7 <- T5 | RateLimiter, RateLimited, NotAuthenticated | consistent |
| T7-T10 tests <- T6 | open_client, https base_url, CSRF header | consistent |
| T11 <- T6 | cookie csrf_token / header X-CSRF-Token / code csrf_failed | consistent |
| T9, T10 <- T7 | ChildSummary, CurrentUser/TutorUser/ParentUser/FamilyMember, families.service read fns | consistent |
| T9 <- T8 | LinkResponse, build_link, create_invitation, create_password_reset | consistent |
| T10 <- T9 | set_child_account | consistent |
| T13-T16 <- T11 | ErrorType=ApiError, safeNext, homeFor, makeQueryClient | consistent |
| T13-T16 <- T12 | applyApiErrors, errorMessage, PasswordField, CopyLinkCard | consistent |
| T16 <- T15 | AppHeader, LogoutButton | consistent |

## Pre-flight: per-task self-consistency
| Task | Finding |
|---|---|
| T1 | ok |
| T2 | ok (test_cli_database_unreachable sets env vars; ENV_FILES can't override env) |
| T3 | test_deleting_family_cascades: after DB-level CASCADE the identity map still holds Child → `db_session.get` returns stale object → Ruling R2 |
| T4 | ok |
| T5 | ok |
| T6 | ok |
| T7 | Files omit tests/factories.py (login helper) → R1 |
| T8 | ok |
| T9 | `tutor_client` fixture referenced but not placed → Ruling R3 |
| T10 | ok |
| T11 | ok |
| T12 | ok |
| T13 | proxy.test.ts uses NextRequest; jsdom env may lack Request internals → Ruling R4 |
| T14 | ok |
| T15 | ok |
| T16 | ok |
| T17 | browser walkthrough needs the in-app browser; implementer subagents may not have it → Ruling R5 |

Pre-flight: Ruling R1: T7 also modifies backend/tests/factories.py to add login() — T7 Produces it — cost if wrong: none
Pre-flight: Ruling R2: T3 cascade test must `db_session.expunge_all()` (or query with populate_existing) before asserting Child is gone — otherwise it reads the identity map, not the DB — cost if wrong: none
Pre-flight: Ruling R3: `tutor_client` fixture lives in backend/tests/families/conftest.py (make_tutor + login on `client`) — only T9/T10 tests use it — cost if wrong: none
Pre-flight: Ruling R4: frontend/src/proxy.test.ts starts with `// @vitest-environment node` — NextRequest needs Node's fetch primitives — cost if wrong: none
Pre-flight: Ruling R5: T17 split — implementer writes the README section; controller performs the browser walkthrough itself (verification only, no code changes); any defect found becomes a fix dispatch — cost if wrong: walkthrough evidence comes from controller, not a fresh agent

## Progress
Task 1: minor (deferred): test_health_access_log_is_debug only asserts INFO absence — add DEBUG-level presence check
Task 1: minor (deferred): no test that all operationIds are unique / free of `_api_` suffix (plan-mandated test scope)
Task 1: Ruling: subagent commits carry their own model trailer (e.g. "Claude Sonnet 5.5") instead of the plan's "Claude Opus 5.5" — the trailer should name the model that authored the commit — cost if wrong: cosmetic commit metadata
Task 1: complete (commits fa85bdb..d84efc6, review clean)
Task 2: Ruling: omitted "parol" from common list — brief requires every entry >= 6 chars and "parol" has 5; parol123/parol1234 included — cost if wrong: none
Task 2: minor (deferred): duplicate line 12121212 in common_passwords.txt
Task 2: minor (deferred): cli maps every IntegrityError to "Репетитор уже создан" (a concurrent duplicate-email insert would get the same text)
Task 2: complete (commits d84efc6..f11ac03, review clean)
Task 3: minor (deferred → carry to T7): Invitation.family_id FK to families.id but app.auth.models doesn't import app.families.models — production process must import families models before flushing an Invitation (T7 makes auth.service import families.service; T7/T8 dispatch must verify app start registers both)
Task 3: minor (deferred): factories.make_child computes `now` unconditionally; is_active=not archived undocumented
Task 3: minor (deferred): no behavioral test for children.user_id ON DELETE SET NULL
Task 3: complete (commits f11ac03..0c5ad7c, review clean)
Task 4: Ruling: reviewer accepted GET+EXPIRE instead of GETEX (TTL depends on role stored in the value) — cost if wrong: none
Task 4: Ruling: plan defect — brief sets the user_sessions index TTL only at create, so an actively-used (sliding) session outlives its index and delete_all_for_user silently misses it; spec 6.1 requires revoking ALL sessions → get() must also refresh the index TTL, and delete_all_for_user must read+drop the index atomically — cost if wrong: one extra EXPIRE per authenticated request
Task 4: fix round 1/5 (2 addressed, 0 open — index TTL refreshed on get; atomic revoke-all; commits b36eec4..a38bb20)
Task 4: minor (deferred): residual race — a login whose credentials were checked before a password change commits but whose session is created after revocation survives (would need a per-user session epoch); final review to judge
Task 4: minor (deferred): get_session_store/get_redis DI wiring uncovered until T7; GETDEL needs Redis >= 6.2 in prod
Task 4: complete (commits 0c5ad7c..a38bb20, review clean after 1 fix round)
Task 5: minor (deferred): retry_after GET+TTL non-atomic (harmless over-estimate)
Task 5: complete (commits a38bb20..70033fa, review clean)
Task 6: minor (deferred): test_csrf.py repeats tokenless-client setup 5x; no tests for PUT/PATCH/DELETE rejected or HEAD/OPTIONS exempt; no assertion that CSRF 403 carries X-Request-ID (middleware order)
Task 6: complete (commits 70033fa..35bfd36, review clean)
Task 7: Ruling: plan-mandated defect — brief's "retry_after first, hit on failure" lets a concurrent burst bypass the login limit entirely (reviewer reproduced 20 parallel attempts all reaching argon2); spec 6.1 requires 5/15min per pair and 30 per IP → reserve atomically before verifying: RateLimiter.hit returns the new count (INCR+EXPIRE NX one pipeline); login INCRs both keys first, 429 if pair>5 or ip>30; on success reset pair and DECR ip (only failures consume the IP budget) — cost if wrong: a 429'd request also consumes a slot (window is fixed, not extended)
Task 7: fix round 1/5 (1 addressed, 0 open — atomic reserve-before-verify rate limit; commits 63d687d..8971f61)
Task 7: minor (deferred): argon2 verify/hash run synchronously on the event loop in login (unauthenticated endpoint) — consider anyio.to_thread
Task 7: minor (deferred): test_app_import_registers_families_tables lives in test_login.py; its last expression asserts nothing
Task 7: minor (deferred): Redis session created before DB commit of last_login_at/rehash (orphan session on commit failure, harmless)
Task 7: minor (deferred): RateLimiter.decr not atomic (DECR+INCR); 429'd attempts still consume the IP budget (fixed window)
Task 7: Ruling: coverage under-counts greenlet-executed SQLAlchemy code (no [tool.coverage.run] concurrency) — fold `concurrency = ["greenlet", "thread"]` into Task 8's dispatch (one-line config, makes the 85% gate honest) — cost if wrong: none
Task 7: complete (commits 35bfd36..8971f61, review clean after 1 fix round)
Task 8: Ruling: reviewer Minor #5 re-graded by effect — our own RequestIdMiddleware access log writes the full path, so live invitation/reset tokens land in JSON logs (account takeover for anyone reading logs within 24h) → fold into Task 9 as an add-on: mask the token segment of /api/auth/invitations/* and /api/auth/password-resets/* in the access log (+ test) — cost if wrong: one extra regex per logged request
Task 8: minor (deferred): POST /auth/password has no rate limit (session holder can guess current password; argon2 on loop)
Task 8: minor (deferred): sessions deleted before DB commit in reset/change — tiny window for a concurrent old-password login to survive
Task 8: minor (deferred): two simultaneous accepts of different invitations with the same email → 500 IntegrityError instead of 409 email_taken
Task 8: minor (deferred): no test for child 6-char minimum in change_password; no FOR UPDATE capture test for reset_password
Task 8: minor (deferred): password_* errors from change_password lack details.field="new_password" (frontend must map codes)
Task 8: minor (deferred): Referrer-Policy: no-referrer on /invite and /reset pages (frontend)
Task 8: complete (commits 8971f61..4801cbd, review clean)
Task 9: Ruling: accepted implementer deviations (extra 409 family_archived/child_archived guards, idempotent archive toggle, username max 64 / q max 200, specific *_not_found codes) — consistent with Task 8 invitation validity and "archived members cannot log in" — cost if wrong: tutor gets 409 where a no-op might be expected
Task 9: minor (deferred): archiving a family doesn't revoke pending invitations — detail still shows pending_invitation, and the old link works again after unarchive
Task 9: minor (deferred): concurrent set_child_account with same username → 500 instead of 409
Task 9: minor (deferred): missing parent email silently "" vs missing child username RuntimeError (inconsistent)
Task 9: minor (deferred): update_family loads members even for name-only edits; meeting URL normalized by HttpUrl (trailing slash/punycode)
Task 9: minor (deferred): tests — birth_year=1990 acceptance; child re-login after family archive
Task 9: complete (commits 4801cbd..3997311, review clean)
Task 10: ⚠️ resolved by controller: get_family_scope doesn't check family archival, but archiving sets all members is_active=False (Task 9) and get_current_user rejects inactive users before scope → no gap
Task 10: minor (deferred): GET /me/children runs 2 queries (scope + list); single-row unpack in set_my_child_account; no child-of-B-sees-A test
Task 10: complete (commits 3997311..eeb6e7c, review clean)
Task 11: ⚠️ resolved by controller: only login's invalid_credentials returns 401 among mutations (suppressed on /login by path check); change_password wrong current → 422; no /forgot page exists
Task 11: minor (deferred): PUBLIC_PATH regex /^\/(login|...)/ lacks boundary (/loginfoo matches); redirect helper in providers.tsx untested (extract loginRedirectUrl)
Task 11: minor (deferred): decodeURIComponent on cookie may throw URIError; no-cookie-after-csrf silently sends without header; concurrent csrf fetches not deduped; no test for abort during csrf fetch
Task 11: complete (commits eeb6e7c..67ed707, review clean)
Task 12: minor (deferred): CopyLinkCard "Скопировано" never resets; clipboard failure shows generic text
Task 12: complete (commits 67ed707..4317f59, review clean)
Task 13: Ruling: accepted afterEach(cleanup) in frontend/vitest.setup.ts — vitest runs without globals so Testing Library never auto-unmounts; global setup fixes it for all files — cost if wrong: none
Task 13: minor (deferred): login-form test fixtures drift from contract (role "student", code "unauthenticated"); "через 0 мин" if retry_after<60 rounds to 0 is impossible (ceil) but <1 → 0; proxy redirect host from request.url behind reverse proxy (plan 7)
Task 13: complete (commits 4317f59..92fbde6, review clean)
Task 14: Ruling: accepted shared applyPasswordPolicyError helper in form-errors.ts (outside file list) — avoids duplicating the code→field mapping across forms; also reused by Task 15 change-password — cost if wrong: none
Task 14: fix round 1/5 (1 addressed, 0 open — one-shot token lookups no longer refetch / data-first render; commits 70f9c38..e2748e1)
Task 14: minor (deferred): repeat-password zod schema near-duplicated across invite/reset; blank card while lookup pending (no loading state); no client-side password minimum
Task 14: complete (commits 92fbde6..e2748e1, review clean after 1 fix round)
Task 15: minor (deferred): no client-side min length for new password; no invalid_username test case; null while children list loads; logout clear() may trigger a /me refetch → harmless double redirect (verify in browser walkthrough)
Task 15: complete (commits e2748e1..10cf2c7, review clean)
Task 16: Ruling: accepted extra files (detail page split into family-parents/invitation/children, edit-family-dialog, reset-link-button, use-refresh-family; shared confirm-dialog.tsx and lib/format.ts) — controller asked to split above ~250 lines — cost if wrong: none
Task 16: minor (deferred): families list URL sync is one-way (nav «Семьи» can't clear filters; back/forward overwritten)
Task 16: minor (deferred): archived child/family still shows actions that always 409; disabled invite button unexplained; null phone/email empty cell; no tests for ConfirmDialog error branch / 409 rendering
Task 16: complete (commits 10cf2c7..2714dc4, review clean)
Task 17: controller browser walkthrough (built-in browser, dev stack from worktree, migration 0001->0002 applied to existing dev volume): all 10 plan steps PASS — tutor login→/admin; family «Тестовые» created; child «Маша» added; invitation link created; logout; invite accepted (prefill shown) → /cabinet shows Маша; parent set login masha.test; child login → /cabinet, nav without «Дети», /admin → /cabinet, GET /api/admin/families → 404; family archived via confirm dialog → parent shown «Заблокирован», parent re-login → «Неверный логин или пароль»; 6th wrong login → «Слишком много попыток. Попробуйте через 15 мин.». Console: only expected 401/404/429 + defect D1.
Task 17: caveat: the browser pane was hidden, so mouse clicks were unreliable after the first few; most steps were driven with element.click()/requestSubmit()/native value setter (exercises app code fully, not physical pointer hit-testing)
Task 17: defects found → fix in the Task 17 dispatch: D1 dev "Could not validate that a segment has instant navigation… dropped segment" on every /admin/* and /cabinet/* page (shells don't render children until /me loads); D2 CreateFamilyDialog stays open inside the hidden <Activity> route after router.push (returning to the list shows it open); D3 accepting an invitation doesn't set last_login_at (tutor sees «Последний вход: —» for a parent who is logged in); D4 create-family name input's accessible name comes from its placeholder (label not associated)
Task 17: controller verified D1 in the browser: fresh load of /admin/families after the fix logs no instant-navigation error (it did before). D4 not reproducible (labels already associated; the placeholder name was an a11y-tree reading artefact)
Task 17: minor (deferred): instant=false comment copied into 6 pages; D4 regression test guards nothing new; reset() redundant in create-family dialog
Task 17: minor (deferred → final review): login/accept/reset forms router.replace into hidden <Activity>; a filled login form (incl. password) may survive hidden and reappear after logout → /login — check in whole-branch review
Task 17: complete (commits 2714dc4..e5cba1a, review clean)
NEXT: final whole-branch review (opus) over fa85bdb..HEAD with deferred-minor list → one fix wave → finishing-a-development-branch
Final review: fresh reviewer (opus) — verdict "With fixes": 1 Critical, 2 Important, 4 Minor; deferred-minor triage done (must-fix: T17 hidden login form, T15 logout refetch, T7 429 consuming IP budget; rest can wait)
Final: Ruling: reverse the Task 9/10 coupling of archival to users.is_active — archive/unarchive no longer flips is_active (is_active = tutor's manual block only); members of an archived family and accounts of archived children are rejected in authenticate() and get_current_user() (and family_scope), sessions are still revoked on archive — fixes "unarchive silently unblocks manually blocked users" — cost if wrong: one extra family/child lookup per authenticated request
Final: Ruling: fold reviewer Minors #4 (parent sees that a child account is blocked) and #5 (seed /me cache after login) into the single fix wave — cheap, in the same code — cost if wrong: none
Final: fixed F1 logout full reload + cleared credentials, F2 archive decoupled from is_active, F3 429 refunds the other counter, F4 parent sees blocked child, F5 /me seeded after login — RED→GREEN each (commits e5cba1a..080b2b5), scoped re-review: all addressed, no new breakage
Final: Ruling: accepted login-page "already signed in" redirect skipping when login.isSuccess (prevents overriding a safe ?next= after seeding /me) — cost if wrong: none
Final: minor (deferred): admin shows «Активен» for members of an archived family (is_active = manual block; family badge «В архиве»); failed logout request gives no toast; plan doc Task 9 text still describes archive flipping is_active; one extra query per parent/child request
