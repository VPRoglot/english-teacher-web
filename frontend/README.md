# Frontend

Next.js 16 (App Router, `cacheComponents`), TanStack Query, Tailwind + shadcn/ui. Общая документация проекта, запуск стека и сценарии проверки — в [../README.md](../README.md).

Перед правками прочитайте [AGENTS.md](AGENTS.md): API Next 16 отличается от старых версий, документация лежит в `node_modules/next/dist/docs/`.

## Команды

Запускаются из корня репозитория или через `pnpm --dir frontend ...`.

| Команда | Что делает |
|---|---|
| `pnpm dev` (`just web`) | dev-сервер на http://localhost:3000; `/api` проксируется на backend, `/media` на MinIO |
| `pnpm build` | production-сборка; проходит без запущенного API (лендинг, `/privacy`, `robots.txt` и `sitemap.xml` читают данные и env во время запроса) |
| `pnpm test` | Vitest + Testing Library |
| `pnpm lint`, `pnpm typecheck` | ESLint, `next typegen` + `tsc` |
| `just gen-api` | OpenAPI из backend → `openapi.json` → типизированный клиент `src/api/generated` (orval); результат коммитится |

## Переменные окружения

Для `pnpm dev` значения берутся из `.env.development` (в git). В Docker они приходят из корневого `.env`, а `API_INTERNAL_URL` задаёт `infra/docker-compose.yml`. Next читает их во время запроса, при сборке они не нужны.

| Переменная | Назначение |
|---|---|
| `API_INTERNAL_URL` | куда серверный код Next ходит за данными лендинга (`http://localhost:8000`, в Docker — `http://api:8000`) |
| `SITE_URL` | публичный адрес сайта без завершающего `/`: canonical, Open Graph, `robots.txt`, `sitemap.xml` |
| `REVALIDATE_SECRET` | секрет для `POST /api/revalidate` (заголовок `Authorization: Bearer ...`); должен совпадать с `REVALIDATE_SECRET` backend |
| `SMARTCAPTCHA_CLIENT_KEY` | необязательный клиентский ключ Yandex SmartCaptcha для формы заявки на `/`; пустой — форма работает без капчи. Серверный ключ (`SMARTCAPTCHA_SERVER_KEY`) нужен backend. В Docker передаётся контейнеру `web` из корневого `.env` |
| `API_PROXY_URL` | только dev: куда проксировать `/api` (в production — nginx) |
| `MEDIA_PROXY_URL` | только dev: куда проксировать `/media` (MinIO, `http://localhost:9000/media`; в production — nginx) |

## Контент сайта

Лендинг получает блоки через `getSite()` (`src/lib/site-content.ts`) с тегом кеша `site-content`. Backend сбрасывает тег запросом на `/api/revalidate` (`src/app/api/revalidate/route.ts`) после сохранения блока в `/admin/site`. Схема и настройка worker — в разделе «Контент сайта» корневого README.

## Заявки

Форма заявки на `/` — `src/components/site/trial-form.tsx` (маска телефона `src/lib/phone-mask.ts`, UTM из URL в `sessionStorage` — `src/lib/utm.ts`, honeypot-поле `website`, невидимая SmartCaptcha). Админка заявок — `/admin/leads` и `/admin/leads/[id]`. Путь заявки, бот Telegram и ключи SmartCaptcha — в разделе «Заявки и уведомления» корневого README.
