#!/usr/bin/env bash
# Интеграционный тест infra/minio/init.sh (compose-проект minio-test).
# Проверяет: повторный запуск, права пользователя приложения (только бакет медиа),
# анонимное чтение, смену пароля приложения, сохранность данных после пересоздания minio,
# отказ работать под root-учёткой и отсутствие секретов в выводе init.sh.
set -euo pipefail
# Git Bash на Windows иначе превращает /init.sh в C:/Program Files/Git/init.sh
export MSYS_NO_PATHCONV=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_SECRET="test-root-secret"
APP_USER="media-app"
APP_SECRET="app-secret-one-1234"
APP_SECRET_NEW="app-secret-two-5678"

host_path() {
	if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}
COMPOSE_FILE_PATH="$(host_path "$HERE/docker-compose.test.yml")"
dc() { docker compose -p minio-test -f "$COMPOSE_FILE_PATH" "$@"; }

cleanup() {
	dc down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

FAILED=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() {
	printf 'FAIL  %s\n' "$1"
	if [ -n "${2:-}" ]; then printf '      %s\n' "$2"; fi
	FAILED=$((FAILED + 1))
}
expect_rc() { # имя фактический_код ожидаемый_код
	if [ "$2" = "$3" ]; then pass "$1"; else fail "$1" "rc=$2 want $3; output: ${OUT:-}"; fi
}
expect_nonzero() {
	if [ "$2" != "0" ]; then pass "$1"; else fail "$1" "rc=0, must fail; output: ${OUT:-}"; fi
}

# Запуск init.sh: код в RC, вывод в OUT, весь вывод копится в INIT_LOG.
INIT_LOG=""
run_init() { # access_key secret_key
	set +e
	OUT="$(dc run --rm -T -e S3_ACCESS_KEY="$1" -e S3_SECRET_KEY="$2" minio-init 2>&1)"
	RC=$?
	set -e
	OUT="$(printf '%s' "$OUT" | tr -d '\r')"
	INIT_LOG+="$OUT"$'\n'
}
# Команда mc в контейнере mc: код в RC, вывод в OUT.
mcx() {
	set +e
	OUT="$(dc exec -T mc mc "$@" 2>&1)"
	RC=$?
	set -e
	OUT="$(printf '%s' "$OUT" | tr -d '\r')"
}
alias_set() { # имя пользователь пароль; повторяет, пока minio не поднимется
	local i
	for i in $(seq 1 60); do
		mcx alias set "$1" http://minio:9000 "$2" "$3"
		if [ "$RC" = 0 ]; then return 0; fi
		sleep 1
	done
	return 1
}
http_code() { # путь
	dc exec -T curl curl -s -o /dev/null -w '%{http_code}' "http://minio:9000/$1" | tr -d '\r'
}

if [ ! -f "$HERE/init.sh" ]; then
	# Иначе docker смонтирует на его месте пустой каталог, и init «пройдёт» вхолостую.
	echo "FAIL  infra/minio/init.sh не найден"
	exit 1
fi

cleanup
dc up -d minio mc curl >/dev/null 2>&1

echo "== init: первый и повторный запуск"
run_init "$APP_USER" "$APP_SECRET"
expect_rc "первый запуск init.sh" "$RC" 0
run_init "$APP_USER" "$APP_SECRET"
expect_rc "повторный запуск init.sh (идемпотентность)" "$RC" 0

echo "== пользователь приложения: чтение и запись в бакет медиа"
alias_set root test-root "$ROOT_SECRET"
alias_set app "$APP_USER" "$APP_SECRET"
expect_rc "alias пользователя приложения" "$RC" 0
dc exec -T mc sh -c 'printf "fake-png-bytes" > /tmp/x.png'
mcx cp /tmp/x.png app/media/x.png
expect_rc "запись в media под пользователем приложения" "$RC" 0
mcx cat app/media/x.png
expect_rc "чтение из media под пользователем приложения" "$RC" 0
if [ "$OUT" = "fake-png-bytes" ]; then pass "содержимое совпадает"; else fail "содержимое совпадает" "got: [$OUT]"; fi

echo "== анонимное чтение"
code="$(http_code media/x.png)"
if [ "$code" = 200 ]; then pass "анонимный GET /media/x.png → 200"; else fail "анонимный GET /media/x.png → 200" "got $code"; fi
code="$(http_code media/)"
if [ "$code" != 200 ]; then pass "анонимный листинг бакета запрещён"; else fail "анонимный листинг бакета запрещён" "got 200"; fi

echo "== пользователь приложения не выходит за бакет медиа"
mcx mb app/other-by-app
expect_nonzero "создание другого бакета запрещено" "$RC"
mcx mb --ignore-existing root/other
mcx cp /tmp/x.png app/other/x.png
expect_nonzero "запись в чужой бакет запрещена" "$RC"
mcx ls app/other
expect_nonzero "листинг чужого бакета запрещён" "$RC"
mcx admin user list app
expect_nonzero "admin-операции запрещены" "$RC"
mcx rm app/media/x.png
expect_nonzero "удаление объекта запрещено" "$RC"
mcx rb --force app/media
expect_nonzero "удаление бакета медиа запрещено" "$RC"
mcx cat root/media/x.png
expect_rc "объект на месте после попыток удаления" "$RC" 0

echo "== смена пароля приложения"
run_init "$APP_USER" "$APP_SECRET_NEW"
expect_rc "init.sh с новым паролем" "$RC" 0
mcx alias set app-new http://minio:9000 "$APP_USER" "$APP_SECRET_NEW"
mcx cat app-new/media/x.png
expect_rc "новый пароль работает" "$RC" 0
mcx cat app/media/x.png
expect_nonzero "старый пароль больше не работает" "$RC"

echo "== данные переживают пересоздание контейнера minio"
dc up -d --force-recreate minio >/dev/null 2>&1
alias_set app-new "$APP_USER" "$APP_SECRET_NEW"
mcx cat app-new/media/x.png
expect_rc "объект читается после пересоздания minio" "$RC" 0

echo "== отказ работать под root-учёткой"
run_init test-root "$ROOT_SECRET"
expect_nonzero "S3_ACCESS_KEY == MINIO_ROOT_USER → ошибка" "$RC"

echo "== секреты не попадают в вывод init.sh"
for secret in "$ROOT_SECRET" "$APP_SECRET" "$APP_SECRET_NEW"; do
	if printf '%s' "$INIT_LOG" | grep -qF -- "$secret"; then
		fail "секрет не в выводе init.sh" "found a secret in init output"
	else
		pass "секрет не в выводе init.sh"
	fi
done

echo
if [ "$FAILED" -eq 0 ]; then
	echo "All minio checks passed"
else
	echo "$FAILED minio check(s) failed"
	exit 1
fi
