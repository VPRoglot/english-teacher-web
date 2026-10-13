# syntax=docker/dockerfile:1
# Playwright с браузерами; версия образа = версия @playwright/test в package.json. Dependabot
# этот образ не обновляет (.github/dependabot.yml): tag@digest меняется вручную в PR с
# @playwright/test.
FROM mcr.microsoft.com/playwright:v1.64.0-noble@sha256:06a9939e57531807f8d5fd76ce44b53165ffb7d7501d87ab10e285c20b1e971f

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /e2e
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY . .
CMD ["pnpm", "exec", "playwright", "test"]
