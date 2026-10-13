import * as Sentry from "@sentry/nextjs";

import { serverSentryOptions } from "@/lib/sentry-options";

/**
 * Серверный Sentry (Node и edge). DSN читается при старте контейнера (`SENTRY_DSN`), а не при
 * сборке: образ один, DSN задаёт `.env` на сервере. Без DSN SDK не инициализируется.
 * Окружение — `SENTRY_ENVIRONMENT` (compose передаёт то же значение, что APP_ENV у backend).
 */
export function register() {
  const options = serverSentryOptions(
    {
      dsn: process.env.SENTRY_DSN,
      environment: process.env.SENTRY_ENVIRONMENT || process.env.NODE_ENV,
      release: process.env.SENTRY_RELEASE,
    },
    // В edge-сборке @sentry/nextjs нет httpIntegration (и нет Http-интеграции по умолчанию).
    process.env.NEXT_RUNTIME === "nodejs" ? Sentry.httpIntegration : undefined,
  );
  if (options.enabled) Sentry.init(options);
}

// Ошибки рендеринга, Route Handlers и Server Actions; без init ничего не отправляет.
export const onRequestError = Sentry.captureRequestError;
