import { withSentryConfig } from "@sentry/nextjs/config";
import type { NextConfig } from "next";

import { SENTRY_TUNNEL_ROUTE } from "./src/lib/sentry-options";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // В production `/api` и `/media` проксирует nginx; в разработке — Next
  // (API_PROXY_URL и MEDIA_PROXY_URL из .env.development).
  async rewrites() {
    const apiProxyUrl = process.env.API_PROXY_URL;
    const mediaProxyUrl = process.env.MEDIA_PROXY_URL;
    return [
      ...(apiProxyUrl ? [{ source: "/api/:path*", destination: `${apiProxyUrl}/api/:path*` }] : []),
      ...(mediaProxyUrl ? [{ source: "/media/:path*", destination: `${mediaProxyUrl}/:path*` }] : []),
    ];
  },
};

// Браузер шлёт события Sentry на свой домен (`/monitoring`), Next проксирует их в sentry.io:
// CSP `connect-src 'self'` не расширяется. Source maps не создаются и не загружаются — у MVP нет
// SENTRY_AUTH_TOKEN; сборка не обращается к Sentry (telemetry выключена, релиз не создаётся).
export default withSentryConfig(nextConfig, {
  tunnelRoute: SENTRY_TUNNEL_ROUTE,
  silent: true,
  telemetry: false,
  sourcemaps: { disable: true },
  release: { create: false, finalize: false },
  // Навигации не трассируются (tracesSampleRate 0, без BrowserTracing) — хук не нужен.
  suppressOnRouterTransitionStartWarning: true,
});
