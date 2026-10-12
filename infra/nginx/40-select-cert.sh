#!/bin/sh
# Выбор сертификата: Let's Encrypt, если certbot его уже выпустил, иначе self-signed.
# /etc/nginx/tls/current — symlink на папку с fullchain.pem и privkey.pem.
# Как /docker-entrypoint.d/40-select-cert.sh выполняется до старта nginx;
# как select-cert (в PATH) дополнительно делает nginx -s reload.
set -eu

tls_dir=/etc/nginx/tls
live_dir="/etc/letsencrypt/live/${SERVER_NAME}"
self_dir="$tls_dir/selfsigned"

# Пара Let's Encrypt годится, если сертификат читается, не просрочен и выпущен на этот ключ.
# Иначе nginx не стартовал бы (или не перечитал конфиг) — лучше остаться на self-signed.
le_pair_ok() {
    [ -s "$live_dir/fullchain.pem" ] && [ -s "$live_dir/privkey.pem" ] || return 1
    if ! cert_pub="$(openssl x509 -in "$live_dir/fullchain.pem" -noout -pubkey 2>/dev/null)"; then
        echo "select-cert: $live_dir/fullchain.pem is not a valid certificate" >&2
        return 1
    fi
    if ! openssl x509 -in "$live_dir/fullchain.pem" -noout -checkend 0 >/dev/null 2>&1; then
        echo "select-cert: $live_dir/fullchain.pem has expired" >&2
        return 1
    fi
    if ! key_pub="$(openssl pkey -in "$live_dir/privkey.pem" -pubout 2>/dev/null)"; then
        echo "select-cert: $live_dir/privkey.pem is not a valid private key" >&2
        return 1
    fi
    if [ "$cert_pub" != "$key_pub" ]; then
        echo "select-cert: $live_dir/privkey.pem does not match fullchain.pem" >&2
        return 1
    fi
}

if le_pair_ok; then
    target="$live_dir"
else
    if [ -e "$live_dir" ]; then
        echo "select-cert: falling back to self-signed certificate" >&2
    fi
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
