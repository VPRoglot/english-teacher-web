#!/bin/sh
# Создаёт репетитора e2e. Выполняется внутри контейнера api (`just e2e`, CI job `e2e`):
#   docker compose … exec -T api sh /e2e/create-tutor.sh
# Email и пароль — из окружения api (infra/e2e.env). Скрипт вместо `sh -c "…"` в justfile:
# PowerShell 5.1 сам подставил бы `$E2E_TUTOR_PASSWORD` и сломал вложенные кавычки.
set -eu

printf '%s\n' "$E2E_TUTOR_PASSWORD" \
    | python -m app.cli create-tutor --email "$E2E_TUTOR_EMAIL" --password-stdin
