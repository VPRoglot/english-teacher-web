# syntax=docker/dockerfile:1
# Клиент mc для minio-init (infra/minio/init.sh): тот же образ Chainguard (вариант -dev с /bin/sh),
# переложенный в наш GHCR как english-tutor-minio-client — сервер не обращается к cgr.dev.
# Digest обновляет Dependabot (экосистема docker, /infra/minio/client).
FROM cgr.dev/chainguard/minio-client:latest-dev@sha256:799f7e86017c3ee8d00f6372e1ee28dd73453f271d5b306a47af8e8a408a777a
