# syntax=docker/dockerfile:1
# MinIO для production: тот же образ Chainguard, переложенный в наш GHCR.
# Сервер не обращается к cgr.dev напрямую (реестр недоступен с российских IP): CD собирает
# этот образ на GitHub и публикует как english-tutor-minio с общим IMAGE_TAG.
# Digest обновляет Dependabot (экосистема docker, /infra/minio/server).
FROM cgr.dev/chainguard/minio:latest@sha256:2136d593beacf4461187035eca949fe49abd589d5079735025c711ca58fee0c8
