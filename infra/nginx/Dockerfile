# syntax=docker/dockerfile:1
FROM nginx:1.31.0-alpine@sha256:2f07d83bf561b506400dc183b1b2003803e39efbd22451f848adaba14d28c7c7

# openssl — для self-signed сертификата, пока certbot не выпустил настоящий.
# default.conf из базового образа заменяется нашим шаблоном.
RUN apk add --no-cache openssl \
    && rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /etc/nginx/tls /etc/letsencrypt /var/www/certbot

# envsubst подставляет только наши переменные: $host, $request_id и т. п. остаются nginx'у.
ENV NGINX_ENVSUBST_FILTER='^(SERVER_NAME|MEDIA_UPSTREAM|MEDIA_UPSTREAM_HOST)$'

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=0755 40-select-cert.sh /docker-entrypoint.d/40-select-cert.sh
COPY --chmod=0755 40-select-cert.sh /usr/local/bin/select-cert
COPY --chmod=0755 90-reload-loop.sh /docker-entrypoint.d/90-reload-loop.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --start-interval=2s --retries=3 \
    CMD wget -qO- http://127.0.0.1/nginx-health || exit 1
