#!/bin/sh
# Ежедневный бэкап PostgreSQL: pg_dump | gzip | age (публичный ключ) -> S3.
# Ключи: backups/daily/YYYY-MM-DD.sql.gz.age и backups/monthly/YYYY-MM.sql.gz.age.
# Хранятся 14 новейших дневных и 6 новейших месячных копий; только что созданная не удаляется.
# После успеха — GET на HEARTBEAT_BACKUP_URL (необязателен; ошибка пинга бэкап не роняет).
# В лог не попадают ни URL heartbeat, ни пароли и ключи.
set -eu
set -o pipefail

DAILY_KEEP=14
MONTHLY_KEEP=6
DAILY_PREFIX="backups/daily/"
MONTHLY_PREFIX="backups/monthly/"
SUFFIX=".sql.gz.age"

log() { printf '%s backup: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() {
	log "ERROR: $*" >&2
	exit 1
}

for var in PGHOST PGUSER PGPASSWORD PGDATABASE BACKUP_S3_BUCKET BACKUP_S3_REGION \
	BACKUP_S3_ACCESS_KEY BACKUP_S3_SECRET_KEY BACKUP_AGE_RECIPIENT S3_BUCKET; do
	eval "value=\${$var:-}"
	[ -n "$value" ] || die "$var is not set"
done
unset value

# Публичный медиа-бакет читается анонимно: бэкапы в нём недопустимы.
[ "$BACKUP_S3_BUCKET" != "$S3_BUCKET" ] || die "BACKUP_S3_BUCKET must differ from S3_BUCKET (public media bucket)"

DATE="${BACKUP_DATE:-$(date -u +%Y-%m-%d)}"
printf '%s' "$DATE" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' || die "BACKUP_DATE must be YYYY-MM-DD"
MONTH="${DATE%-*}"
DAILY_KEY="$DAILY_PREFIX$DATE$SUFFIX"
MONTHLY_KEY="$MONTHLY_PREFIX$MONTH$SUFFIX"

export AWS_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_KEY"
export AWS_DEFAULT_REGION="$BACKUP_S3_REGION"
if [ -n "${BACKUP_S3_ENDPOINT_URL:-}" ]; then
	export AWS_ENDPOINT_URL="$BACKUP_S3_ENDPOINT_URL"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FILE="$TMP/backup$SUFFIX"

log "dumping database $PGDATABASE"
pg_dump --no-owner --format=plain | gzip -9 | age -r "$BACKUP_AGE_RECIPIENT" -o "$FILE"
[ -s "$FILE" ] || die "encrypted dump is empty"
log "encrypted dump: $(wc -c <"$FILE" | tr -d ' ') bytes"

aws s3 cp --only-show-errors "$FILE" "s3://$BACKUP_S3_BUCKET/$DAILY_KEY"
log "uploaded s3://$BACKUP_S3_BUCKET/$DAILY_KEY"

if aws s3api head-object --bucket "$BACKUP_S3_BUCKET" --key "$MONTHLY_KEY" >/dev/null 2>&1; then
	log "monthly copy $MONTHLY_KEY already exists"
else
	aws s3 cp --only-show-errors "s3://$BACKUP_S3_BUCKET/$DAILY_KEY" "s3://$BACKUP_S3_BUCKET/$MONTHLY_KEY"
	log "copied to s3://$BACKUP_S3_BUCKET/$MONTHLY_KEY"
fi

# Ротация: имена содержат дату, поэтому сортировка по имени = по дате.
# Удаляются самые старые сверх $keep; ключ, созданный этим запуском, не удаляется никогда.
rotate() { # префикс шаблон_даты сколько_хранить только_что_созданный_ключ
	prefix="$1"
	pattern="^$(printf '%s' "$prefix" | sed 's/[.]/\\./g')$2$(printf '%s' "$SUFFIX" | sed 's/[.]/\\./g')\$"
	keep="$3"
	current="$4"
	aws s3api list-objects-v2 --bucket "$BACKUP_S3_BUCKET" --prefix "$prefix" \
		--query 'Contents[].Key' --output text >"$TMP/list"
	tr '\t' '\n' <"$TMP/list" | grep -E "$pattern" | sort >"$TMP/keys" || true
	total="$(wc -l <"$TMP/keys" | tr -d ' ')"
	excess=$((total - keep))
	if [ "$excess" -le 0 ]; then
		log "rotation $prefix: $total object(s), nothing to delete"
		return 0
	fi
	head -n "$excess" "$TMP/keys" | while IFS= read -r key; do
		if [ "$key" = "$current" ]; then
			log "rotation $prefix: keeping just-created $key"
			continue
		fi
		aws s3 rm --only-show-errors "s3://$BACKUP_S3_BUCKET/$key"
		log "rotation $prefix: deleted $key"
	done
}
rotate "$DAILY_PREFIX" '[0-9]{4}-[0-9]{2}-[0-9]{2}' "$DAILY_KEEP" "$DAILY_KEY"
rotate "$MONTHLY_PREFIX" '[0-9]{4}-[0-9]{2}' "$MONTHLY_KEEP" "$MONTHLY_KEY"

log "backup $DAILY_KEY done"

if [ -n "${HEARTBEAT_BACKUP_URL:-}" ]; then
	# URL — секрет: ни он, ни сообщения wget (в них есть адрес) не выводятся.
	if wget -q -T 10 -O /dev/null "$HEARTBEAT_BACKUP_URL" >/dev/null 2>&1; then
		log "heartbeat sent"
	else
		log "heartbeat failed (backup itself succeeded)" >&2
	fi
fi
