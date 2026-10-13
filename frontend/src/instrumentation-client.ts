import * as Sentry from "@sentry/nextjs";

import { browserSentryOptions } from "@/lib/sentry-options";

// Браузерный Sentry. NEXT_PUBLIC_* встраиваются в бандл при сборке (ARG в Dockerfile).
// События уходят только через туннель /monitoring (см. browserSentryOptions).
const options = browserSentryOptions({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  // То же окружение, что у сервера и backend (prod); в CD — build arg NEXT_PUBLIC_SENTRY_ENVIRONMENT.
  environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || process.env.NODE_ENV,
  release: process.env.NEXT_PUBLIC_SENTRY_RELEASE,
});
if (options.enabled) Sentry.init(options);
