#!/bin/sh
# Восстановление зашифрованного бэкапа в пустую базу PGDATABASE.
#   restore.sh <ключ объекта> <путь к age-identity>
# Например: restore.sh backups/daily/2026-09-21.sql.gz.age /run/secrets/age.key
# Приватный ключ хранится у владельца вне сервера и монтируется только на время восстановления.
# Если в схеме public есть таблицы, восстановление отказывается работать.
set -eu
set -o pipefail

log() { printf '%s restore: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() {
	log "ERROR: $*" >&2
	exit 1
}

[ "$#" -eq 2 ] || die "usage: restore.sh <object key> <age identity file>"
KEY="$1"
IDENTITY="$2"
[ -r "$IDENTITY" ] || die "age identity file $IDENTITY is not readable"

for var in PGHOST PGUSER PGPASSWORD PGDATABASE BACKUP_S3_BUCKET BACKUP_S3_REGION \
	BACKUP_S3_ACCESS_KEY BACKUP_S3_SECRET_KEY; do
	eval "value=\${$var:-}"
	[ -n "$value" ] || die "$var is not set"
done
unset value

export AWS_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_KEY"
export AWS_DEFAULT_REGION="$BACKUP_S3_REGION"
if [ -n "${BACKUP_S3_ENDPOINT_URL:-}" ]; then
	export AWS_ENDPOINT_URL="$BACKUP_S3_ENDPOINT_URL"
fi

TABLES="$(psql -X -v ON_ERROR_STOP=1 -tAq -c "select count(*) from pg_tables where schemaname = 'public'")"
[ "$TABLES" = "0" ] || die "database $PGDATABASE is not empty ($TABLES table(s) in schema public); restore only into an empty database"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

log "downloading s3://$BACKUP_S3_BUCKET/$KEY"
aws s3 cp --only-show-errors "s3://$BACKUP_S3_BUCKET/$KEY" "$TMP/backup.sql.gz.age"

# Сначала расшифровка и проверка архива целиком: в базу не попадёт обрезанный дамп.
age -d -i "$IDENTITY" -o "$TMP/backup.sql.gz" "$TMP/backup.sql.gz.age"
gzip -t "$TMP/backup.sql.gz"

log "restoring into database $PGDATABASE"
gunzip -c "$TMP/backup.sql.gz" | psql -X -q -v ON_ERROR_STOP=1 --single-transaction >/dev/null
log "restore of $KEY into $PGDATABASE done"
