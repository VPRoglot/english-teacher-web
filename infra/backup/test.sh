#!/usr/bin/env bash
# Интеграционный тест образа english-tutor-backup.
# Compose-проект backup-test: postgres + MinIO (бакеты backups и media) + заглушка heartbeat + backup.
# Проверяет шифрование дампа, ротацию 14/6, восстановление в пустую базу, отказ восстановления
# в непустую базу, запрет BACKUP_S3_BUCKET == S3_BUCKET и heartbeat только после успеха.
set -euo pipefail
# Git Bash на Windows иначе превращает /usr/... в C:/Program Files/Git/usr/...
export MSYS_NO_PATHCONV=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="/tmp/backup-test-age.key" # приватный ключ живёт только в тестовом контейнере
HB_SECRET="hb-secret-token-42"
HB_URL="http://heartbeat:8080/ping/?key=$HB_SECRET"
DAILY_PREFIX="backups/daily/"
MONTHLY_PREFIX="backups/monthly/"

# Путь для docker.exe: на Windows нужен C:/..., а не /c/...
host_path() {
	if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}
COMPOSE_FILE_PATH="$(host_path "$HERE/docker-compose.test.yml")"
dc() { docker compose -p backup-test -f "$COMPOSE_FILE_PATH" "$@"; }

cleanup() {
	dc down -v --remove-orphans >/dev/null 2>&1 || true
}

FAILED=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() {
	printf 'FAIL  %s\n' "$1"
	if [ -n "${2:-}" ]; then printf '      %s\n' "$2"; fi
	FAILED=$((FAILED + 1))
}
expect_eq() { # имя фактическое ожидаемое
	if [ "$2" = "$3" ]; then pass "$1"; else fail "$1" "got: [$2] want: [$3]"; fi
}
expect_ne() {
	if [ "$2" != "$3" ]; then pass "$1"; else fail "$1" "got: [$2], must differ"; fi
}
expect_contains() { # имя текст подстрока
	if printf '%s' "$2" | grep -qF -- "$3"; then pass "$1"; else fail "$1" "[$3] not in: [$2]"; fi
}
expect_not_contains() {
	if printf '%s' "$2" | grep -qF -- "$3"; then fail "$1" "[$3] unexpectedly in: [$2]"; else pass "$1"; fi
}

# Команда в контейнере backup (переменные окружения — через -e перед командой).
bx() { dc exec -T "$@"; }
# aws-cli в контейнере backup с тестовыми учётными данными MinIO.
s3() {
	dc exec -T \
		-e AWS_ACCESS_KEY_ID=test-access-key -e AWS_SECRET_ACCESS_KEY=test-secret-key \
		-e AWS_DEFAULT_REGION=us-east-1 -e AWS_ENDPOINT_URL=http://minio:9000 \
		backup aws "$@"
}
# Ключи объектов бакета с префиксом, по одному на строку, по возрастанию.
keys() { # бакет префикс
	s3 s3api list-objects-v2 --bucket "$1" --prefix "$2" --query 'Contents[].Key' --output text |
		tr -d '\r' | tr '\t' '\n' | grep -v '^None$' | sed '/^$/d' | sort || true
}
psql_in() { # база sql
	dc exec -T postgres psql -U tutor -d "$1" -XtAq -v ON_ERROR_STOP=1 -c "$2" | tr -d '\r'
}
heartbeat_hits() {
	dc logs --no-log-prefix heartbeat 2>&1 | grep -cF "GET /ping/?key=$HB_SECRET " || true
}
# Запуск backup.sh: код возврата в RC, вывод (stdout+stderr) в OUT.
run_backup() { # доп. аргументы для docker compose exec (-e ...)
	set +e
	OUT="$(bx -e BACKUP_AGE_RECIPIENT="$RECIPIENT" "$@" backup backup.sh 2>&1)"
	RC=$?
	set -e
	OUT="$(printf '%s' "$OUT" | tr -d '\r')"
	ALL_RUNS_OUT+="$OUT"$'\n' # для проверки, что секреты не попадают в вывод
}
ALL_RUNS_OUT=""
run_restore() { # база ключ_объекта
	set +e
	OUT="$(bx -e PGDATABASE="$1" backup restore.sh "$2" "$KEY_FILE" 2>&1)"
	RC=$?
	set -e
	OUT="$(printf '%s' "$OUT" | tr -d '\r')"
}

trap cleanup EXIT
cleanup

dc build
dc up -d

echo "--- 0. image"
expect_eq "CMD is crond -f -d 8" "$(docker inspect -f '{{json .Config.Cmd}}' english-tutor-backup:test)" '["crond","-f","-d","8"]'
expect_eq "crontab runs backup.sh daily at 02:30" \
	"$(bx backup sh -c 'grep -v "^#" /etc/crontabs/root | sed "/^$/d"' | tr -d '\r')" "30 2 * * * /usr/local/bin/backup.sh"
expect_contains "crond is running" "$(bx backup ps -o args | tr -d '\r')" "crond -f -d 8"
# Сообщения самого crond (в том числе ошибки) идут в stderr контейнера, а не в syslog.
expect_contains "crond logs to docker logs" "$(dc logs --no-color backup 2>&1)" "crond (busybox"
expect_eq "age is installed" "$(bx backup sh -c 'command -v age >/dev/null && command -v age-keygen >/dev/null && echo ok' | tr -d '\r' || true)" "ok"

echo "--- 1. source data"
psql_in tutor "create table items (id integer primary key, name text not null, created_at timestamptz not null);
insert into items select g, md5(g::text), timestamptz '2026-01-01' + g * interval '1 minute' from generate_series(1, 1000) g;" >/dev/null
SNAPSHOT_SQL="select count(*) || ':' || md5(string_agg(id || '|' || name || '|' || created_at, ',' order by id)) from items"
SRC="$(psql_in tutor "$SNAPSHOT_SQL")"
expect_eq "source table has 1000 rows" "${SRC%%:*}" "1000"

echo "--- 2. age key"
bx backup age-keygen -o "$KEY_FILE" >/dev/null 2>&1
RECIPIENT="$(bx backup age-keygen -y "$KEY_FILE" | tr -d '\r')"
if [[ "$RECIPIENT" =~ ^age1[0-9a-z]+$ ]]; then pass "recipient generated"; else fail "recipient generated" "$RECIPIENT"; fi

echo "--- 3. fake old backups"
bx backup sh -c '
	set -eu
	rm -rf /tmp/fake && mkdir -p /tmp/fake/daily /tmp/fake/monthly
	for d in $(seq 1 20); do : > "/tmp/fake/daily/2026-09-$(printf %02d "$d").sql.gz.age"; done
	for m in $(seq 1 8); do : > "/tmp/fake/monthly/2026-0$m.sql.gz.age"; done
'
s3 s3 cp --quiet --recursive /tmp/fake s3://backups/backups >/dev/null
expect_eq "20 fake daily objects" "$(keys backups "$DAILY_PREFIX" | wc -l | tr -d ' ')" "20"
expect_eq "8 fake monthly objects" "$(keys backups "$MONTHLY_PREFIX" | wc -l | tr -d ' ')" "8"

echo "--- 4. backup.sh with BACKUP_DATE=2026-09-21"
run_backup -e BACKUP_DATE=2026-09-21 -e HEARTBEAT_BACKUP_URL="$HB_URL"
expect_eq "backup.sh exits 0" "$RC" "0"
expect_contains "log says heartbeat sent" "$OUT" "heartbeat sent"
printf '%s\n' "$OUT" | sed 's/^/      | /'

echo "--- 5. retention and encryption"
DAILY="$(keys backups "$DAILY_PREFIX")"
expect_eq "exactly 14 daily objects" "$(printf '%s\n' "$DAILY" | wc -l | tr -d ' ')" "14"
expect_eq "oldest kept daily is 2026-09-08" "$(printf '%s\n' "$DAILY" | head -n 1)" "${DAILY_PREFIX}2026-09-08.sql.gz.age"
expect_eq "newest daily is 2026-09-21" "$(printf '%s\n' "$DAILY" | tail -n 1)" "${DAILY_PREFIX}2026-09-21.sql.gz.age"
MONTHLY="$(keys backups "$MONTHLY_PREFIX")"
expect_eq "exactly 6 monthly objects" "$(printf '%s\n' "$MONTHLY" | wc -l | tr -d ' ')" "6"
expect_eq "monthly are the 6 newest (2026-04..2026-09)" "$(printf '%s\n' "$MONTHLY" | sed "s|^$MONTHLY_PREFIX||; s|\.sql\.gz\.age$||" | paste -sd ' ' -)" \
	"2026-04 2026-05 2026-06 2026-07 2026-08 2026-09"
HEAD="$(s3 s3 cp s3://backups/backups/daily/2026-09-21.sql.gz.age - | head -c 64 | head -n 1 | tr -d '\r' || true)"
expect_eq "daily object starts with age header" "$HEAD" "age-encryption.org/v1"
expect_ne "daily object is not a plain dump (PGDMP)" "${HEAD:0:5}" "PGDMP"
expect_ne "daily object is not plain SQL (--)" "${HEAD:0:2}" "--"
MHEAD="$(s3 s3 cp s3://backups/backups/monthly/2026-09.sql.gz.age - | head -c 64 | head -n 1 | tr -d '\r' || true)"
expect_eq "monthly copy is the encrypted dump too" "$MHEAD" "age-encryption.org/v1"
expect_eq "media bucket untouched" "$(keys media "" | wc -l | tr -d ' ')" "0"

echo "--- 6. restore into empty database"
psql_in tutor "create database restored" >/dev/null
run_restore restored backups/daily/2026-09-21.sql.gz.age
expect_eq "restore.sh exits 0" "$RC" "0"
printf '%s\n' "$OUT" | sed 's/^/      | /'
expect_eq "restored rows and md5 match the source" "$(psql_in restored "$SNAPSHOT_SQL" 2>&1 || true)" "$SRC"

echo "--- 7. restore into non-empty database is refused"
run_restore restored backups/daily/2026-09-21.sql.gz.age
expect_ne "second restore.sh exits non-zero" "$RC" "0"
expect_contains "refusal explains the database is not empty" "$OUT" "not empty"
expect_eq "restored database unchanged" "$(psql_in restored "$SNAPSHOT_SQL" 2>&1 || true)" "$SRC"

echo "--- 8. backup bucket equal to media bucket"
DAILY_BEFORE="$(keys backups "$DAILY_PREFIX")"
run_backup -e BACKUP_DATE=2026-09-22 -e BACKUP_S3_BUCKET=media -e S3_BUCKET=media -e HEARTBEAT_BACKUP_URL="$HB_URL"
expect_ne "BACKUP_S3_BUCKET == S3_BUCKET -> non-zero" "$RC" "0"
expect_contains "error names the bucket clash" "$OUT" "must differ"
expect_not_contains "fails before pg_dump" "$OUT" "dump"
expect_eq "no objects in media bucket" "$(keys media "" | wc -l | tr -d ' ')" "0"
expect_eq "backups bucket unchanged" "$(keys backups "$DAILY_PREFIX")" "$DAILY_BEFORE"

echo "--- 9. heartbeat only after success, never logged"
expect_eq "successful backup pinged heartbeat once (failed run did not)" "$(heartbeat_hits)" "1"
run_backup -e BACKUP_DATE=2026-09-22 -e PGHOST=no-such-host -e HEARTBEAT_BACKUP_URL="$HB_URL"
expect_ne "pg_dump failure -> non-zero" "$RC" "0"
expect_eq "pg_dump failure: no heartbeat" "$(heartbeat_hits)" "1"
expect_eq "pg_dump failure: nothing uploaded" "$(keys backups "$DAILY_PREFIX")" "$DAILY_BEFORE"
run_backup -e BACKUP_DATE=2026-09-21 -e HEARTBEAT_BACKUP_URL="$HB_URL"
expect_eq "re-run for the same date exits 0" "$RC" "0"
expect_contains "log says heartbeat sent" "$OUT" "heartbeat sent"
expect_eq "second success pinged heartbeat" "$(heartbeat_hits)" "2"
expect_eq "re-run keeps 14 daily" "$(keys backups "$DAILY_PREFIX" | wc -l | tr -d ' ')" "14"
expect_eq "re-run keeps 6 monthly" "$(keys backups "$MONTHLY_PREFIX" | wc -l | tr -d ' ')" "6"
run_backup -e BACKUP_DATE=2026-09-21 -e HEARTBEAT_BACKUP_URL="http://no-such-host:8080/ping/?key=$HB_SECRET"
expect_eq "unreachable heartbeat does not fail the backup" "$RC" "0"
expect_contains "unreachable heartbeat is logged" "$OUT" "heartbeat failed"
ALL_OUT="$(dc logs --no-log-prefix backup 2>&1; printf '%s' "$ALL_RUNS_OUT")"
expect_not_contains "heartbeat URL never printed" "$ALL_OUT" "$HB_SECRET"
expect_not_contains "secret key never printed" "$ALL_OUT" "test-secret-key"
expect_not_contains "db password never printed" "$ALL_OUT" "test-password"

echo "--- 10. just-created backup is never rotated away"
run_backup -e BACKUP_DATE=2026-01-05
expect_eq "backup with an old date exits 0" "$RC" "0"
DAILY="$(keys backups "$DAILY_PREFIX")"
expect_contains "2026-01-05 daily kept although older than the 14 newest" "$DAILY" "${DAILY_PREFIX}2026-01-05.sql.gz.age"
expect_contains "newest daily 2026-09-21 still kept" "$DAILY" "${DAILY_PREFIX}2026-09-21.sql.gz.age"
expect_eq "14 newest + the just-created one" "$(printf '%s\n' "$DAILY" | wc -l | tr -d ' ')" "15"
expect_contains "just-created monthly 2026-01 kept too" "$(keys backups "$MONTHLY_PREFIX")" "${MONTHLY_PREFIX}2026-01.sql.gz.age"

echo
if [ "$FAILED" -ne 0 ]; then
	echo "backup container logs (tail):"
	dc logs --tail 50 backup 2>&1 || true
	echo "$FAILED check(s) FAILED"
	exit 1
fi
echo "All backup checks passed"
