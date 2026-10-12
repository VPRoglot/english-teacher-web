#!/usr/bin/env bash
# Интеграционный тест образа english-tutor-nginx.
# Поднимает в сети nginx-test собранный образ, заглушки api/web и клиент curl,
# проверяет редирект, ACME, TLS-заголовки, X-Forwarded-*, X-Request-ID, лимит тела,
# ленивый DNS upstream'ов, маскирование токенов в логе и выбор сертификата.
set -euo pipefail
# Git Bash на Windows иначе превращает /etc/... в C:/Program Files/Git/etc/...
export MSYS_NO_PATHCONV=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="english-tutor-nginx:test"
CURL_IMAGE="curlimages/curl:8.17.0@sha256:935d9100e9ba842cdb060de42472c7ca90cfe9a7c96e4dacb55e79e560b3ff40"
NET="nginx-test"
NGINX="nginx-test-nginx"
API="nginx-test-api"
API2="nginx-test-api2"
WEB="nginx-test-web"
CLIENT="nginx-test-client"
DOMAIN="tutor.test"
CSP="default-src 'self'; script-src 'self' 'unsafe-inline' https://smartcaptcha.yandexcloud.net; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://smartcaptcha.yandexcloud.net; font-src 'self' data:; connect-src 'self' https://smartcaptcha.yandexcloud.net; frame-src https://smartcaptcha.yandexcloud.net; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests"

# Путь для docker.exe: на Windows нужен C:/..., а не /c/...
host_path() {
	if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

cleanup() {
	docker rm -f "$NGINX" "$API" "$API2" "$WEB" "$CLIENT" >/dev/null 2>&1 || true
	docker network rm "$NET" >/dev/null 2>&1 || true
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
expect_contains() { # имя текст подстрока
	if printf '%s' "$2" | grep -qF -- "$3"; then pass "$1"; else fail "$1" "[$3] not in: [$2]"; fi
}
expect_not_contains() {
	if printf '%s' "$2" | grep -qF -- "$3"; then fail "$1" "[$3] unexpectedly in: [$2]"; else pass "$1"; fi
}
expect_match() { # имя текст ERE
	if printf '%s' "$2" | grep -qE -- "$3"; then pass "$1"; else fail "$1" "/$3/ not in: [$2]"; fi
}

cx() { docker exec "$CLIENT" curl -sS --max-time 10 "$@"; }
code() { cx -o /dev/null -w '%{http_code}' "$@" 2>/dev/null || true; }
# Значение заголовка ответа (без CR); $1 — имя заголовка, дальше аргументы curl.
header() {
	local name="$1"
	shift
	cx -o /dev/null -D - "$@" | tr -d '\r' | sed -n "s/^${name}: //Ip" || true
}
cert_subject() {
	cx -vk -o /dev/null "https://$DOMAIN/" 2>&1 | sed -n 's/^\*[[:space:]]*subject: //p' || true
}

start_stub() { # имя_контейнера сетевой_алиас
	docker create --name "$1" --network "$NET" --network-alias "$2" "$BASE_IMAGE" >/dev/null
	tar -C "$HERE" -cf - test-upstream.conf | docker cp - "$1:/etc/nginx/conf.d/"
	docker start "$1" >/dev/null
}
container_ip() {
	docker inspect -f "{{(index .NetworkSettings.Networks \"$NET\").IPAddress}}" "$1"
}
wait_for() { # секунды команда... — ждёт, пока команда не вернёт 0
	local deadline=$((SECONDS + $1))
	shift
	until "$@"; do
		if [ "$SECONDS" -ge "$deadline" ]; then return 1; fi
		sleep 1
	done
}

trap cleanup EXIT
cleanup

docker build -t "$IMAGE" "$(host_path "$HERE")"
# Заглушки — на том же закреплённом базовом образе, что и наш Dockerfile.
BASE_IMAGE="$(sed -n 's/^FROM[[:space:]]\{1,\}\([^[:space:]]\{1,\}\).*/\1/p' "$HERE/Dockerfile" | head -n 1)"
docker pull -q "$BASE_IMAGE" >/dev/null
docker pull -q "$CURL_IMAGE" >/dev/null

docker network create "$NET" >/dev/null
# nginx стартует раньше upstream'ов: имена api/web резолвятся лениво, на запросе.
docker run -d --name "$NGINX" --network "$NET" --network-alias "$DOMAIN" \
	-e SERVER_NAME="$DOMAIN" \
	-e MEDIA_UPSTREAM="http://web:3000/bucket" \
	-e MEDIA_UPSTREAM_HOST="media.test" \
	"$IMAGE" >/dev/null
start_stub "$API" api
start_stub "$WEB" web
docker run -d --name "$CLIENT" --network "$NET" --entrypoint sleep "$CURL_IMAGE" 3600 >/dev/null
CLIENT_IP="$(container_ip "$CLIENT")"

nginx_up() { [ "$(code "http://$DOMAIN/nginx-health")" = "200" ]; }
if ! wait_for 30 nginx_up; then
	docker logs "$NGINX" || true
	echo "nginx did not start" >&2
	exit 1
fi

echo "--- 0. healthcheck"
expect_eq "/nginx-health on :80 is 200 (not redirected)" "$(code "http://$DOMAIN/nginx-health")" "200"
healthy() { [ "$(docker inspect -f '{{.State.Health.Status}}' "$NGINX")" = "healthy" ]; }
if wait_for 30 healthy; then pass "docker HEALTHCHECK reports healthy"; else fail "docker HEALTHCHECK reports healthy" "$(docker inspect -f '{{json .State.Health}}' "$NGINX")"; fi

echo "--- 1. http -> https redirect"
expect_eq "http://$DOMAIN/x -> 301 https://$DOMAIN/x" \
	"$(cx -o /dev/null -w '%{http_code} %{redirect_url}' "http://$DOMAIN/x?a=1" || true)" "301 https://$DOMAIN/x?a=1"

echo "--- 2. ACME webroot"
docker exec "$NGINX" sh -c 'mkdir -p /var/www/certbot/.well-known/acme-challenge && printf acme-token-content > /var/www/certbot/.well-known/acme-challenge/t'
expect_eq "acme-challenge served from webroot over http" \
	"$(cx "http://$DOMAIN/.well-known/acme-challenge/t" || true)" "acme-token-content"

echo "--- 3. TLS + security headers"
HEADERS="$(cx -k -o /dev/null -D - "https://$DOMAIN/" | tr -d '\r' || true)"
expect_match "https / -> 200" "$HEADERS" '^HTTP/[0-9.]+ 200'
expect_match "HSTS max-age=31536000 without includeSubDomains" "$HEADERS" '^(s|S)trict-(t|T)ransport-(s|S)ecurity: max-age=31536000$'
expect_eq "CSP is exactly the agreed policy" "$(header Content-Security-Policy -k "https://$DOMAIN/")" "$CSP"
expect_contains "CSP has frame-ancestors 'none'" "$HEADERS" "frame-ancestors 'none'"
expect_contains "CSP allows SmartCaptcha" "$HEADERS" "https://smartcaptcha.yandexcloud.net"
expect_eq "X-Content-Type-Options: nosniff" "$(header X-Content-Type-Options -k "https://$DOMAIN/")" "nosniff"
expect_eq "Referrer-Policy" "$(header Referrer-Policy -k "https://$DOMAIN/")" "strict-origin-when-cross-origin"
expect_eq "X-Frame-Options: DENY" "$(header X-Frame-Options -k "https://$DOMAIN/")" "DENY"
expect_eq "Permissions-Policy" "$(header Permissions-Policy -k "https://$DOMAIN/")" "camera=(), microphone=(), geolocation=()"
expect_eq "Server header has no version" "$(header Server -k "https://$DOMAIN/")" "nginx"
expect_eq "/ is proxied to web:3000" "$(header X-Upstream-Port -k "https://$DOMAIN/")" "3000"
expect_eq "/_next/static/ is proxied to web:3000" "$(header X-Upstream-Port -k "https://$DOMAIN/_next/static/a.js")" "3000"
expect_eq "/_next/static/ cached for 1y" "$(header Cache-Control -k "https://$DOMAIN/_next/static/a.js")" "max-age=31536000"

echo "--- 4. X-Forwarded-*, X-Request-ID"
RESP="$(cx -k -D - -H 'X-Forwarded-For: 1.2.3.4' "https://$DOMAIN/api/x" | tr -d '\r' || true)"
BODY="$(printf '%s\n' "$RESP" | tail -n 1)"
IFS='|' read -r XFF PROTO RID HOST <<<"$BODY" || true
expect_eq "/api/ is proxied to api:8000" "$(printf '%s\n' "$RESP" | sed -n 's/^x-upstream-port: //Ip')" "8000"
expect_eq "X-Forwarded-For is overwritten with client address" "$XFF" "$CLIENT_IP"
expect_not_contains "spoofed 1.2.3.4 does not reach upstream" "$BODY" "1.2.3.4"
expect_eq "X-Forwarded-Proto is https" "$PROTO" "https"
expect_eq "Host is passed through" "$HOST" "$DOMAIN"
expect_match "generated X-Request-ID is 32 hex" "$RID" '^[0-9a-f]{32}$'
RESP_IDS="$(printf '%s\n' "$RESP" | sed -n 's/^x-request-id: //Ip')"
expect_eq "response has exactly one X-Request-ID, equal to upstream's" "$RESP_IDS" "$RID"
VALID_ID="abc.DEF_123-xyz"
BODY="$(cx -k -H "X-Request-ID: $VALID_ID" "https://$DOMAIN/api/x" || true)"
expect_eq "valid client X-Request-ID passes unchanged" "$(printf '%s' "$BODY" | cut -d'|' -f3)" "$VALID_ID"
expect_eq "valid client X-Request-ID echoed in response" "$(header X-Request-ID -k -H "X-Request-ID: $VALID_ID" "https://$DOMAIN/api/x")" "$VALID_ID"
BAD_ID="bad id;<script>"
BODY="$(cx -k -H "X-Request-ID: $BAD_ID" "https://$DOMAIN/api/x" || true)"
expect_match "invalid client X-Request-ID replaced by 32 hex" "$(printf '%s' "$BODY" | cut -d'|' -f3)" '^[0-9a-f]{32}$'
LONG_ID="$(printf 'a%.0s' $(seq 1 65))"
BODY="$(cx -k -H "X-Request-ID: $LONG_ID" "https://$DOMAIN/api/x" || true)"
expect_match "65-char client X-Request-ID replaced by 32 hex" "$(printf '%s' "$BODY" | cut -d'|' -f3)" '^[0-9a-f]{32}$'

echo "--- 4b. /media/"
BODY="$(cx -k -H 'Cookie: session=s3cr3t' "https://$DOMAIN/media/dir/a%20b.png?x=1" || true)"
expect_eq "/media/<key> -> MEDIA_UPSTREAM/<key> with MEDIA_UPSTREAM_HOST, no cookies" "$BODY" "media|/bucket/dir/a%20b.png|media.test|"
expect_eq "/media/ cached for 7d" "$(header Cache-Control -k "https://$DOMAIN/media/a.png")" "max-age=604800"
expect_eq "/media/ HEAD allowed" "$(code -k -I "https://$DOMAIN/media/a.png")" "200"
expect_eq "/media/ POST rejected" "$(code -k -X POST -d x "https://$DOMAIN/media/a.png")" "405"
expect_eq "security headers also on media" "$(header X-Content-Type-Options -k "https://$DOMAIN/media/a.png")" "nosniff"
expect_match "media: single nginx X-Request-ID (upstream's hidden)" "$(header X-Request-ID -k "https://$DOMAIN/media/a.png")" '^[0-9a-f]{32}$'

echo "--- 5. body size limit"
post_size() { # байты
	docker exec "$CLIENT" sh -c "head -c $1 /dev/zero | curl -sS -k --max-time 30 -o /dev/null -w '%{http_code}' --data-binary @- https://$DOMAIN/api/admin/media" || true
}
expect_eq "POST 7 MB -> 413" "$(post_size $((7 * 1024 * 1024)))" "413"
expect_eq "POST 5 MB -> 200" "$(post_size $((5 * 1024 * 1024)))" "200"
expect_match "413 still carries HSTS (add_header always)" \
	"$(docker exec "$CLIENT" sh -c "head -c 7340032 /dev/zero | curl -sS -k -o /dev/null -D - --data-binary @- https://$DOMAIN/api/admin/media" | tr -d '\r' || true)" \
	'^(s|S)trict-(t|T)ransport-(s|S)ecurity: max-age=31536000$'

echo "--- 6. api re-created with a new IP"
OLD_IP="$(container_ip "$API")"
# Новый контейнер поднимается до удаления старого, поэтому IP гарантированно другой.
start_stub "$API2" api
NEW_IP="$(container_ip "$API2")"
docker rm -f "$API" >/dev/null
if [ "$OLD_IP" = "$NEW_IP" ]; then fail "precondition: new api IP differs" "$OLD_IP"; fi
api_ok() { [ "$(code -k "https://$DOMAIN/api/x")" = "200" ]; }
STARTED=$SECONDS
if wait_for 15 api_ok; then
	pass "/api/x is 200 again $((SECONDS - STARTED)) s after api moved $OLD_IP -> $NEW_IP"
else
	fail "/api/x is 200 again within 15 s after api moved $OLD_IP -> $NEW_IP"
fi

echo "--- 7. tokens masked in access log"
code "http://$DOMAIN/invite/SECRET123" >/dev/null
code -k "https://$DOMAIN/invite/SECRET123" >/dev/null
code -k "https://$DOMAIN/reset/SECRET123?x=1" >/dev/null
code -k "https://$DOMAIN/api/auth/invitations/SECRET123" >/dev/null
code -k -X POST "https://$DOMAIN/api/auth/invitations/SECRET123/accept" >/dev/null
code -k "https://$DOMAIN/api/auth/password-resets/SECRET123" >/dev/null
code -k -e "https://$DOMAIN/invite/SECRET123" "https://$DOMAIN/_next/static/b.js" >/dev/null
sleep 1
LOGS="$(docker logs "$NGINX" 2>&1)"
expect_not_contains "SECRET123 never appears in nginx logs" "$LOGS" "SECRET123"
expect_contains "/invite/*** logged" "$LOGS" '"/invite/***"'
expect_contains "/reset/*** logged (query kept)" "$LOGS" '"/reset/***?x=1"'
expect_contains "/api/auth/invitations/***/accept logged" "$LOGS" '"/api/auth/invitations/***/accept"'
expect_contains "/api/auth/password-resets/*** logged" "$LOGS" '"/api/auth/password-resets/***"'
expect_contains "referer masked" "$LOGS" "https://$DOMAIN/invite/***"
expect_match "access log is JSON with request_id" "$LOGS" '^\{"time":.*"request_id":"[A-Za-z0-9._-]+"'

echo "--- 8. certificate selection"
SUBJECT="$(cert_subject)"
expect_eq "without letsencrypt cert nginx serves self-signed for $DOMAIN" "$SUBJECT" "CN=$DOMAIN"
if docker exec "$NGINX" openssl x509 -in /etc/nginx/tls/selfsigned/fullchain.pem -noout -checkend $((29 * 86400)) >/dev/null &&
	! docker exec "$NGINX" openssl x509 -in /etc/nginx/tls/selfsigned/fullchain.pem -noout -checkend $((31 * 86400)) >/dev/null; then
	pass "self-signed cert is valid for 30 days"
else
	fail "self-signed cert is valid for 30 days"
fi
docker exec "$NGINX" sh -c "mkdir -p /etc/letsencrypt/live/$DOMAIN && openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj /CN=planted-letsencrypt -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem 2>/dev/null"
docker exec "$NGINX" select-cert
planted() { [ "$(cert_subject)" = "CN=planted-letsencrypt" ]; }
if wait_for 10 planted; then pass "after select-cert nginx serves the letsencrypt cert"; else fail "after select-cert nginx serves the letsencrypt cert" "$(cert_subject)"; fi
expect_eq "tls/current points to letsencrypt live dir" \
	"$(docker exec "$NGINX" readlink /etc/nginx/tls/current)" "/etc/letsencrypt/live/$DOMAIN"
expect_eq "site still works after reload" "$(code -k "https://$DOMAIN/")" "200"
expect_contains "6-hourly reload loop is running" "$(docker exec "$NGINX" ps -o args)" "sleep 21600"

echo
if [ "$FAILED" -ne 0 ]; then
	echo "nginx logs (tail):"
	docker logs --tail 50 "$NGINX" 2>&1 || true
	echo "$FAILED check(s) FAILED"
	exit 1
fi
echo "All nginx checks passed"
