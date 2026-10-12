#!/bin/sh
# Выбор сертификата: Let's Encrypt, если certbot его уже выпустил, иначе self-signed.
# /etc/nginx/tls/current — symlink на папку с fullchain.pem и privkey.pem.
# Как /docker-entrypoint.d/40-select-cert.sh выполняется до старта nginx;
# как select-cert (в PATH) дополнительно делает nginx -s reload.
set -eu

tls_dir=/etc/nginx/tls
live_dir="/etc/letsencrypt/live/${SERVER_NAME}"
self_dir="$tls_dir/selfsigned"

if [ -s "$live_dir/fullchain.pem" ] && [ -s "$live_dir/privkey.pem" ]; then
    target="$live_dir"
else
    target="$self_dir"
    # Генерируется один раз; заново — только если истекает в ближайшие сутки.
    if [ ! -s "$self_dir/fullchain.pem" ] || [ ! -s "$self_dir/privkey.pem" ] \
        || ! openssl x509 -in "$self_dir/fullchain.pem" -noout -checkend 86400 >/dev/null 2>&1; then
        mkdir -p "$self_dir"
        openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
            -subj "/CN=${SERVER_NAME}" -addext "subjectAltName=DNS:${SERVER_NAME}" \
            -keyout "$self_dir/privkey.pem" -out "$self_dir/fullchain.pem" 2>/dev/null
        chmod 600 "$self_dir/privkey.pem"
    fi
fi

mkdir -p "$tls_dir"
ln -sfn "$target" "$tls_dir/current"
echo "select-cert: using $target"

if [ "$(basename "$0")" = "select-cert" ]; then
    nginx -s reload
fi
