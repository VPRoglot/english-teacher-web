#!/bin/sh
# Раз в 6 часов перевыбирает сертификат и перечитывает его (select-cert делает nginx -s reload):
# так подхватываются и первый выпуск, и продления certbot без перезапуска контейнера.
set -eu

(
    while :; do
        sleep 21600
        select-cert || echo "reload-loop: select-cert failed" >&2
    done
) &
