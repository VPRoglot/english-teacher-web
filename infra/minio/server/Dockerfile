# syntax=docker/dockerfile:1
# MinIO для production: тот же образ Chainguard, переложенный в наш GHCR.
# Сервер не обращается к cgr.dev напрямую (реестр недоступен с российских IP): CD собирает
# этот образ на GitHub и публикует как english-tutor-minio с общим IMAGE_TAG.
# Digest обновляет Dependabot (экосистема docker, /infra/minio/server).
FROM cgr.dev/chainguard/minio:latest@sha256:dc455cdd4db6e390b1b26514f15ff37681a777bf8dab41aac445a0259f751e56
