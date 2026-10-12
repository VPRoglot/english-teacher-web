#!/usr/bin/env bash
# Тест infra/scripts/deploy.sh на заглушках: docker, git и curl (и flock, если его нет в системе,
# как в Git Bash на Windows) пишут вызовы в журнал, поведение задаётся переменными FAKE_*.
# Скрипт копируется во временный «репозиторий» и запускается оттуда: DEPLOY_DIR вычисляется
# от расположения скрипта. Настоящие docker и git не вызываются.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy.sh"
A="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
B="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
COMPOSE="docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml"
CURL="curl -fsS -k --max-time 5 --resolve tutor.example.com:443:127.0.0.1"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BIN="$TMP/bin"
REPO="$TMP/repo"
LOG="$TMP/calls.log"
OUT="$TMP/out.log"
mkdir -p "$BIN"

# --- заглушки ---------------------------------------------------------------------------------
# docker: в журнал попадает и IMAGE_TAG из .env на момент вызова (cwd = DEPLOY_DIR).
cat >"$BIN/docker" <<'EOF'
#!/usr/bin/env bash
tag="$(grep -E '^IMAGE_TAG=' .env 2>/dev/null | head -n1 | cut -d= -f2-)"
echo "docker $* [IMAGE_TAG=$tag]" >>"$FAKE_LOG"
case " $* " in
  *" pull "*) [ "${FAKE_PULL_FAIL:-0}" = 1 ] && exit 1 ;;
  *" run --rm migrate"*) [ "${FAKE_MIGRATE_FAIL:-0}" = 1 ] && exit 1 ;;
  *" up "*) [ -n "${FAKE_UP_FAIL_TAG:-}" ] && [ "$tag" = "$FAKE_UP_FAIL_TAG" ] && exit 1 ;;
esac
exit 0
EOF
cat >"$BIN/git" <<'EOF'
#!/usr/bin/env bash
echo "git $*" >>"$FAKE_LOG"
exit 0
EOF
cat >"$BIN/curl" <<'EOF'
#!/usr/bin/env bash
echo "curl $*" >>"$FAKE_LOG"
[ "${FAKE_CURL_FAIL:-0}" = 1 ] && exit 22
exit 0
EOF
REAL_FLOCK=0
if command -v flock >/dev/null 2>&1; then
  REAL_FLOCK=1
else
  # Нет util-linux (Git Bash): заглушка «занято» по FAKE_FLOCK_BUSY=1.
  cat >"$BIN/flock" <<'EOF'
#!/usr/bin/env bash
echo "flock $*" >>"$FAKE_LOG"
[ "${FAKE_FLOCK_BUSY:-0}" = 1 ] && exit 1
exit 0
EOF
fi
chmod +x "$BIN"/*

# --- помощники --------------------------------------------------------------------------------
FAILS=0
pass() { echo "ok   - $1"; }
fail() {
  echo "FAIL - $1" >&2
  echo "  --- calls:" >&2
  sed 's/^/  /' "$LOG" >&2 || true
  echo "  --- output:" >&2
  sed 's/^/  /' "$OUT" >&2 || true
  FAILS=$((FAILS + 1))
}

# Новый «репозиторий»: скрипт в infra/scripts, .env с прежним тегом. Журнал очищается.
setup() {
  rm -rf "$REPO"
  mkdir -p "$REPO/infra/scripts"
  cp "$SRC" "$REPO/infra/scripts/deploy.sh" 2>/dev/null || true
  printf '%s\n' \
    '# prod' \
    'DOMAIN=tutor.example.com' \
    "IMAGE_TAG=sha-$A" \
    'POSTGRES_PASSWORD=keep-me' >"$REPO/.env"
  cp "$REPO/.env" "$TMP/env.orig"
  : >"$LOG"
  : >"$OUT"
}

# Запуск из чужого каталога: DEPLOY_DIR должен вычислиться от пути скрипта.
CODE=0
deploy() {
  set +e
  (cd "$TMP" && env PATH="$BIN:$PATH" FAKE_LOG="$LOG" \
    DEPLOY_SMOKE_ATTEMPTS="${DEPLOY_SMOKE_ATTEMPTS:-2}" DEPLOY_SMOKE_INTERVAL=0 \
    bash "$REPO/infra/scripts/deploy.sh" "$@") >"$OUT" 2>&1
  CODE=$?
  set -e
}

# Строки журнала, совпадающие с регулярками (grep -E), идут именно в этом порядке.
in_order() {
  local from=0 pattern n
  for pattern in "$@"; do
    n="$(tail -n +"$((from + 1))" "$LOG" | grep -nE -m1 -- "$pattern" | cut -d: -f1 || true)"
    if [ -z "$n" ]; then
      echo "  missing (in order): $pattern" >&2
      return 1
    fi
    from=$((from + n))
  done
}
count() { grep -cE -- "$1" "$LOG" || true; }
env_tag() { grep -E '^IMAGE_TAG=' "$REPO/.env" | cut -d= -f2- | tr '\n' ' ' | sed 's/ $//'; }
re() { printf '%s' "$1" | sed 's/[.[\*^$/]/\\&/g'; }

CMP="^$(re "$COMPOSE")"
READY="^$(re "$CURL") https://tutor\.example\.com/api/health/ready$"
ROOT="^$(re "$CURL") https://tutor\.example\.com/$"

# --- 1. успех ---------------------------------------------------------------------------------
setup
deploy "$B"
if [ "$CODE" = 0 ] &&
  in_order "^git fetch --prune origin$" "^git checkout --detach $B$" \
    "$CMP pull \[IMAGE_TAG=sha-$B\]$" "$CMP run --rm migrate \[IMAGE_TAG=sha-$B\]$" \
    "$CMP up -d --no-build --remove-orphans \[IMAGE_TAG=sha-$B\]$" "$READY" "$ROOT" &&
  [ "$(env_tag)" = "sha-$B" ] && grep -qx 'POSTGRES_PASSWORD=keep-me' "$REPO/.env" &&
  grep -qx 'DOMAIN=tutor.example.com' "$REPO/.env" && [ "$(count ' up ')" = 1 ]; then
  pass "success: fetch, checkout, pull, migrate, up, smoke; IMAGE_TAG=sha-bbb…; exit 0"
else
  fail "success scenario (exit $CODE, IMAGE_TAG=$(env_tag))"
fi

# --- 2. smoke падает → откат ------------------------------------------------------------------
setup
FAKE_CURL_FAIL=1 deploy "$B"
if [ "$CODE" = 1 ] &&
  in_order "^git checkout --detach $B$" "$CMP up -d --no-build --remove-orphans \[IMAGE_TAG=sha-$B\]$" \
    "$READY" "$READY" "^git checkout --detach $A$" \
    "$CMP up -d --no-build --remove-orphans \[IMAGE_TAG=sha-$A\]$" &&
  [ "$(count "$READY")" = 2 ] && [ "$(count ' up ')" = 2 ] &&
  [ "$(env_tag)" = "sha-$A" ] && cmp -s "$REPO/.env" "$TMP/env.orig"; then
  pass "smoke fails: IMAGE_TAG=sha-aaa… restored, checkout aaa…, second up; exit 1"
else
  fail "smoke failure rollback (exit $CODE, IMAGE_TAG=$(env_tag))"
fi

# --- 3. pull падает → .env не изменён, up не вызывался ----------------------------------------
setup
FAKE_PULL_FAIL=1 deploy "$B"
if [ "$CODE" = 1 ] && cmp -s "$REPO/.env" "$TMP/env.orig" &&
  [ "$(count ' up ')" = 0 ] && [ "$(count 'run --rm migrate')" = 0 ] &&
  in_order "^git checkout --detach $B$" "$CMP pull " "^git checkout --detach $A$"; then
  pass "pull fails: .env unchanged, no up, commit restored; exit 1"
else
  fail "pull failure (exit $CODE, IMAGE_TAG=$(env_tag))"
fi

# --- 3a. migrate падает → откат без up --------------------------------------------------------
setup
FAKE_MIGRATE_FAIL=1 deploy "$B"
if [ "$CODE" = 1 ] && cmp -s "$REPO/.env" "$TMP/env.orig" && [ "$(count ' up ')" = 0 ] &&
  in_order "$CMP run --rm migrate " "^git checkout --detach $A$"; then
  pass "migrate fails: .env restored, no up, commit restored; exit 1"
else
  fail "migrate failure (exit $CODE, IMAGE_TAG=$(env_tag))"
fi

# --- 3b. откат тоже не удался → exit 2 --------------------------------------------------------
setup
FAKE_CURL_FAIL=1 FAKE_UP_FAIL_TAG="sha-$A" deploy "$B"
if [ "$CODE" = 2 ] && [ "$(count ' up ')" = 2 ] && grep -q 'откат' "$OUT"; then
  pass "rollback up fails: exit 2"
else
  fail "rollback failure (exit $CODE)"
fi

# --- 4. неверный аргумент → exit 2, ничего не вызвано -----------------------------------------
for args in "main" "abc1234" "${B^^}" "${B}0" "" "$B $B"; do
  setup
  # shellcheck disable=SC2086 # нарочно: пустая строка — запуск без аргументов, два слова — два аргумента
  deploy $args
  if [ "$CODE" = 2 ] && [ ! -s "$LOG" ] && cmp -s "$REPO/.env" "$TMP/env.orig"; then
    pass "invalid argument '${args:0:12}': exit 2, nothing called"
  else
    fail "invalid argument '$args' (exit $CODE)"
  fi
done

# --- 5. в .env нет IMAGE_TAG (или он не sha-<40 hex>, или нет DOMAIN) → exit 2 ----------------
check_bad_env() {
  local name="$1" expect="$2"
  if [ "$CODE" = 2 ] && [ "$(count '^(git|docker|curl) ')" = 0 ] && grep -q -- "$expect" "$OUT"; then
    pass "$name: exit 2, clear message, nothing called"
  else
    fail "$name (exit $CODE)"
  fi
}
setup
sed -i '/^IMAGE_TAG=/d' "$REPO/.env"
deploy "$B"
check_bad_env "no IMAGE_TAG in .env" "IMAGE_TAG"
setup
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=latest/' "$REPO/.env"
deploy "$B"
check_bad_env "IMAGE_TAG=latest in .env" "IMAGE_TAG"
setup
sed -i '/^DOMAIN=/d' "$REPO/.env"
deploy "$B"
check_bad_env "no DOMAIN in .env" "DOMAIN"
setup
rm "$REPO/.env"
deploy "$B"
check_bad_env "no .env" ".env"

# --- 6. второй деплой, пока идёт первый → exit 2 «деплой уже идёт» ----------------------------
setup
if [ "$REAL_FLOCK" = 1 ]; then
  # Настоящий flock: тест держит блокировку .deploy.lock, пока запускается deploy.sh.
  exec 8>"$REPO/.deploy.lock"
  flock -n 8
  deploy "$B" 8>&-
  exec 8>&-
else
  FAKE_FLOCK_BUSY=1 deploy "$B"
fi
if [ "$CODE" = 2 ] && grep -q 'деплой уже идёт' "$OUT" &&
  [ "$(count '^(git|docker|curl) ')" = 0 ] && cmp -s "$REPO/.env" "$TMP/env.orig"; then
  pass "concurrent deploy (real flock: $REAL_FLOCK): exit 2, 'деплой уже идёт'"
else
  fail "concurrent deploy (exit $CODE)"
fi

if [ "$FAILS" -gt 0 ]; then
  echo "test-deploy: $FAILS check(s) failed" >&2
  exit 1
fi
echo "test-deploy: all checks passed"
