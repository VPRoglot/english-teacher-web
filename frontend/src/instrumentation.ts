import * as Sentry from "@sentry/nextjs";

import { sentryOptions } from "@/lib/sentry-options";

/**
 * Серверный Sentry (Node и edge). DSN читается при старте контейнера (`SENTRY_DSN`), а не при
 * сборке: образ один, DSN задаёт `.env` на сервере. Без DSN SDK не инициализируется.
 */
export function register() {
  const options = sentryOptions({
    dsn: process.env.SENTRY_DSN,
    environment: process.env.NODE_ENV,
    release: process.env.SENTRY_RELEASE,
  });
  if (options.enabled) Sentry.init(options);
}

// Ошибки рендеринга, Route Handlers и Server Actions; без init ничего не отправляет.
export const onRequestError = Sentry.captureRequestError;
