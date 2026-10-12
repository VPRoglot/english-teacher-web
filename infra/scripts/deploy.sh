#!/usr/bin/env bash
# Деплой релиза на сервер: deploy.sh <git-sha из 40 hex>.
#
#   git fetch → git checkout --detach <sha> → IMAGE_TAG=sha-<sha> в .env → compose pull →
#   compose run --rm migrate → compose up -d → smoke-проверка /api/health/ready и / через nginx.
#
# При любой ошибке после checkout — откат: прежний IMAGE_TAG в .env, прежний коммит
# (он же sha из прежнего тега) и, если up уже запускался, снова up -d на старых образах.
# Схема БД не откатывается: миграции только расширяющие и совместимы с прошлым релизом.
#
# Коды выхода: 0 — новый релиз работает; 1 — релиз не удался, откат выполнен (или ничего
# не менялось); 2 — неверные аргументы/.env, деплой уже идёт или откат не удался.
#
# Окружение: DEPLOY_DIR (по умолчанию — корень репозитория, от расположения скрипта),
# DEPLOY_SMOKE_ATTEMPTS (30), DEPLOY_SMOKE_INTERVAL (2 с).
# На сервере нужны bash, git, docker compose v2, curl, flock (util-linux).
set -euo pipefail

log() { printf '%s deploy: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die2() {
  log "ОШИБКА: $*"
  exit 2
}

if [ "$#" -ne 1 ] || ! [[ "$1" =~ ^[0-9a-f]{40}$ ]]; then
  die2 "использование: deploy.sh <git-sha: 40 символов 0-9a-f>"
fi
new_sha="$1"
new_tag="sha-$new_sha"

attempts="${DEPLOY_SMOKE_ATTEMPTS:-30}"
interval="${DEPLOY_SMOKE_INTERVAL:-2}"
[[ "$attempts" =~ ^[1-9][0-9]*$ ]] || die2 "DEPLOY_SMOKE_ATTEMPTS должно быть целым > 0"
[[ "$interval" =~ ^[0-9]+$ ]] || die2 "DEPLOY_SMOKE_INTERVAL должно быть целым ≥ 0"

DEPLOY_DIR="${DEPLOY_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$DEPLOY_DIR" || die2 "нет каталога DEPLOY_DIR=$DEPLOY_DIR"

# Один деплой за раз: второй сразу выходит, а не ждёт (CI не должен висеть).
exec 9>>.deploy.lock
flock -n 9 || die2 "деплой уже идёт (занят $DEPLOY_DIR/.deploy.lock)"

[ -f .env ] || die2 "нет файла $DEPLOY_DIR/.env"

# Значение KEY=... из .env (без source: .env не обязан быть корректным shell-скриптом).
env_value() {
  local v
  v="$(grep -E "^$1=" .env | tail -n1 | cut -d= -f2-)" || true
  v="${v%$'\r'}"
  v="${v#\"}"
  v="${v%\"}"
  printf '%s' "$v"
}

tag_lines="$(grep -cE '^IMAGE_TAG=' .env || true)"
[ "$tag_lines" = 1 ] || die2 "в .env должна быть ровно одна строка IMAGE_TAG=sha-<40 hex> (найдено: $tag_lines)"
prev_tag="$(env_value IMAGE_TAG)"
[[ "$prev_tag" =~ ^sha-[0-9a-f]{40}$ ]] ||
  die2 "IMAGE_TAG в .env должен быть sha-<40 hex> (сейчас: '$prev_tag'): по нему находится коммит для отката"
prev_sha="${prev_tag#sha-}"

domain="$(env_value DOMAIN)"
[[ "$domain" =~ ^[A-Za-z0-9.-]+$ ]] || die2 "в .env не задан DOMAIN (нужен для smoke-проверки)"

compose() {
  docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml "$@"
}

set_tag() {
  sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$1/" .env
  [ "$(env_value IMAGE_TAG)" = "$1" ]
}

# Приложение через nginx на этом хосте; сертификат не проверяется (-k): его и доступность
# снаружи проверяет внешний uptime-монитор.
smoke() {
  local i path ok
  for ((i = 1; i <= attempts; i++)); do
    ok=1
    for path in /api/health/ready /; do
      if ! curl -fsS -k --max-time 5 --resolve "$domain:443:127.0.0.1" "https://$domain$path" >/dev/null; then
        ok=0
        break
      fi
    done
    if [ "$ok" = 1 ]; then
      return 0
    fi
    log "smoke: попытка $i/$attempts не прошла"
    if [ "$i" -lt "$attempts" ]; then
      sleep "$interval"
    fi
  done
  return 1
}

checked_out=0
tag_changed=0
up_started=0

rollback() {
  local ok=1 tag_ok=1
  if [ "$tag_changed" = 1 ]; then
    set_tag "$prev_tag" || { ok=0; tag_ok=0; log "не удалось вернуть IMAGE_TAG=$prev_tag в .env"; }
  fi
  if [ "$checked_out" = 1 ]; then
    git checkout --detach "$prev_sha" || { ok=0; log "не удалось вернуть коммит $prev_sha"; }
  fi
  if [ "$up_started" = 1 ]; then
    if [ "$tag_ok" = 1 ]; then
      compose up -d --no-build --remove-orphans || { ok=0; log "не удалось поднять $prev_tag"; }
    else
      ok=0
    fi
  fi
  [ "$ok" = 1 ]
}

abort() {
  trap - INT TERM HUP
  log "релиз $new_tag не удался: $*"
  if [ "$checked_out" = 0 ]; then
    log "ничего не изменено"
    exit 1
  fi
  log "откат на $prev_tag"
  if rollback; then
    log "откат выполнен: работает $prev_tag"
    exit 1
  fi
  log "ОШИБКА: откат не удался — нужна ручная проверка сервера"
  exit 2
}
trap 'abort "прервано сигналом"' INT TERM HUP

log "деплой $new_tag (сейчас $prev_tag) в $DEPLOY_DIR"
git fetch --prune origin || abort "git fetch"
git checkout --detach "$new_sha" || abort "git checkout $new_sha"
checked_out=1
tag_changed=1
set_tag "$new_tag" || abort "замена IMAGE_TAG в .env"
compose pull || abort "compose pull"
compose run --rm migrate || abort "миграции"
up_started=1
compose up -d --no-build --remove-orphans || abort "compose up"
smoke || abort "smoke-проверка https://$domain/api/health/ready и /"
trap - INT TERM HUP
log "готово: работает $new_tag"
