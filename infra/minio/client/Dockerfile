# syntax=docker/dockerfile:1
# Клиент mc для minio-init (infra/minio/init.sh): тот же образ Chainguard (вариант -dev с /bin/sh),
# переложенный в наш GHCR как english-tutor-minio-client — сервер не обращается к cgr.dev.
# Digest обновляет Dependabot (экосистема docker, /infra/minio/client).
FROM cgr.dev/chainguard/minio-client:latest-dev@sha256:4ded9b0773ebf1afded36c4e91efad0d4e7dee91c6b3d5d29455732095afb2d0
