import * as Sentry from "@sentry/nextjs";

import { browserSentryOptions } from "@/lib/sentry-options";

// Браузерный Sentry. NEXT_PUBLIC_* встраиваются в бандл при сборке (ARG в Dockerfile).
// События уходят только через туннель /monitoring (см. browserSentryOptions).
const options = browserSentryOptions({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NODE_ENV,
  release: process.env.NEXT_PUBLIC_SENTRY_RELEASE,
});
if (options.enabled) Sentry.init(options);
