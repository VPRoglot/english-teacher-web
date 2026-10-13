#!/bin/sh
# Подготовка MinIO для фото лендинга. Запускается сервисом minio-init при каждом `up`,
# поэтому каждая команда безопасна при повторе:
#   - бакет ${S3_BUCKET} с анонимным чтением объектов (так nginx отдаёт /media/);
#   - пользователь приложения ${S3_ACCESS_KEY} (повтор обновляет пароль);
#   - политика app-media-rw: чтение и загрузка только в ${S3_BUCKET}, привязана к пользователю.
# Root-учётка MinIO нужна только здесь; приложение работает под своим пользователем.
# Секреты не печатаются: вывод mc глушится, в лог идут только шаги.
set -eu

: "${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"
: "${S3_BUCKET:?S3_BUCKET is required}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"
MINIO_URL="${MINIO_URL:-http://minio:9000}"
POLICY=app-media-rw

log() { echo "minio-init: $*"; }

if [ "$S3_ACCESS_KEY" = "$MINIO_ROOT_USER" ]; then
	log "S3_ACCESS_KEY совпадает с MINIO_ROOT_USER: приложение не должно работать под root" >&2
	exit 1
fi

# MinIO может ещё стартовать: ждём до 60 секунд.
tries=0
until mc alias set root "$MINIO_URL" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
	tries=$((tries + 1))
	if [ "$tries" -ge 60 ]; then
		log "MinIO недоступен по $MINIO_URL" >&2
		exit 1
	fi
	sleep 1
done
log "MinIO доступен"

policy_file="$(mktemp)"
anon_file="$(mktemp)"
trap 'rm -f "$policy_file" "$anon_file"' EXIT

mc mb --ignore-existing "root/$S3_BUCKET" >/dev/null
# Анонимно — только чтение объекта по ключу. Готовая политика `download` разрешает ещё и
# листинг бакета, а список всех файлов посторонним не нужен.
cat >"$anon_file" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": ["*"]},
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::${S3_BUCKET}/*"]
    }
  ]
}
EOF
mc anonymous set-json "$anon_file" "root/$S3_BUCKET" >/dev/null
log "бакет $S3_BUCKET готов, анонимное чтение объектов включено"

# Приложение только загружает фото (S3MediaStorage.put) и не удаляет их:
# без DeleteObject утечка учётки приложения не позволит стереть медиа.
cat >"$policy_file" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::${S3_BUCKET}"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": ["arn:aws:s3:::${S3_BUCKET}/*"]
    }
  ]
}
EOF
mc admin policy create root "$POLICY" "$policy_file" >/dev/null
log "политика $POLICY обновлена"

mc admin user add root "$S3_ACCESS_KEY" "$S3_SECRET_KEY" >/dev/null
# Повторная привязка уже привязанной политики — не ошибка.
if ! out="$(mc admin policy attach root "$POLICY" --user "$S3_ACCESS_KEY" 2>&1)"; then
	case "$out" in
	*"already in effect"* | *"already attached"*) ;;
	*)
		log "не удалось привязать политику $POLICY" >&2
		exit 1
		;;
	esac
fi
log "пользователь приложения готов"
