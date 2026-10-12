# syntax=docker/dockerfile:1
# Тот же мажор PostgreSQL, что и у базы: pg_dump/psql 16.
FROM postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea

# aws-cli — загрузка в S3, age — шифрование дампа на публичный ключ владельца.
RUN apk add --no-cache aws-cli age

# S3-совместимые хранилища не всегда принимают CRC-контрольные суммы,
# которые aws-cli v2 добавляет по умолчанию: только там, где их требует API.
ENV AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
    AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
    AWS_PAGER=""

COPY --chmod=0755 backup.sh restore.sh /usr/local/bin/
COPY --chmod=0600 crontab /etc/crontabs/root

# crond из busybox работает от root внутри контейнера, портов нет.
# Окружение контейнера передаётся заданиям, их вывод попадает в docker logs.
ENTRYPOINT []
CMD ["crond", "-f"]
