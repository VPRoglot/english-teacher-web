import type { Breadcrumb, BrowserOptions, ErrorEvent, getDefaultIntegrations } from "@sentry/nextjs";

// @sentry/core — транзитивная зависимость: типы берём через публичный API @sentry/nextjs.
type TransactionEvent = Parameters<NonNullable<BrowserOptions["beforeSendTransaction"]>>[0];
type Integration = ReturnType<typeof getDefaultIntegrations>[number];

/** Путь туннеля: тот же, что `tunnelRoute` в next.config.ts. */
export const SENTRY_TUNNEL_ROUTE = "/monitoring";

const MASK = "***";
// Те же правила, что `scrub_text` в backend/app/core/observability.py: одноразовые токены из
// ссылок приглашения и сброса пароля и токен Telegram-бота не должны попадать в Sentry.
const SECRET_PATTERNS: readonly RegExp[] = [
  /(\/(?:invite|reset|api\/auth\/invitations|api\/auth\/password-resets)\/)[^/?#\s"']+/g,
  /(api\.telegram\.org\/bot)[^/?#\s"']+/g,
];
const DROPPED_HEADERS = new Set(["cookie", "set-cookie", "authorization", "x-csrf-token"]);
// Только DSN sentry.io: для них `@sentry/nextjs` создаёт rewrite туннеля на ingest-хост.
const SAAS_DSN_HOST = /^o(\d+)\.ingest(?:\.([a-z]{2}))?\.sentry\.io$/;

export function scrubUrl(url: string): string {
  return SECRET_PATTERNS.reduce((text, pattern) => text.replace(pattern, `$1${MASK}`), url);
}

function scrubDeep(value: unknown): unknown {
  if (typeof value === "string") return scrubUrl(value);
  if (Array.isArray(value)) return value.map(scrubDeep);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, scrubDeep(item)]));
  }
  return value;
}

function dropSecretHeaders(request: Record<string, unknown>): void {
  delete request.cookies;
  const headers = request.headers;
  if (headers !== null && typeof headers === "object") {
    request.headers = Object.fromEntries(
      Object.entries(headers).filter(([name]) => !DROPPED_HEADERS.has(name.toLowerCase())),
    );
  }
}

/** Маскирует токены во всех строках события (URL, transaction, Referer, сообщения, breadcrumbs). */
function scrubEvent<T extends ErrorEvent | TransactionEvent>(event: T): T {
  const result = scrubDeep(event) as T;
  if (result.request) dropSecretHeaders(result.request as Record<string, unknown>);
  return result;
}

function scrubBreadcrumb(crumb: Breadcrumb): Breadcrumb {
  return scrubDeep(crumb) as Breadcrumb;
}

export interface SentryEnv {
  dsn?: string;
  environment?: string;
  release?: string;
}

/** Общие настройки Sentry для сервера и браузера. Пустая строка считается незаданной. */
export function sentryOptions(env: SentryEnv) {
  const dsn = env.dsn || undefined;
  return {
    dsn,
    enabled: Boolean(dsn),
    environment: env.environment || undefined,
    release: env.release || undefined,
    sendDefaultPii: false,
    // Только ошибки: трассировка не нужна MVP, а в именах транзакций были бы URL с токенами.
    tracesSampleRate: 0,
    beforeSend: (event: ErrorEvent): ErrorEvent => scrubEvent(event),
    beforeSendTransaction: (event: TransactionEvent): TransactionEvent => scrubEvent(event),
    beforeBreadcrumb: (crumb: Breadcrumb): Breadcrumb => scrubBreadcrumb(crumb),
  };
}

/**
 * Путь туннеля для DSN sentry.io — тот же, что строит `@sentry/nextjs` (`?o=<org>&p=<project>`).
 * Для других хостов (GlitchTip, self-hosted) туннеля нет — undefined.
 */
export function tunnelFor(dsn: string): string | undefined {
  let url: URL;
  try {
    url = new URL(dsn);
  } catch {
    return undefined;
  }
  const match = SAAS_DSN_HOST.exec(url.hostname);
  const projectId = url.pathname.split("/").filter(Boolean).at(-1);
  if (!match || !projectId || !/^\d+$/.test(projectId)) return undefined;
  const [, orgId, region] = match;
  return `${SENTRY_TUNNEL_ROUTE}?o=${orgId}&p=${projectId}${region ? `&r=${region}` : ""}`;
}

/**
 * Браузер: события идут только через туннель `/monitoring` (CSP `connect-src 'self'`).
 * DSN без туннеля отключает отправку — иначе SDK пошёл бы на ingest-хост напрямую.
 */
export function browserSentryOptions(env: SentryEnv) {
  const base = sentryOptions(env);
  const tunnel = base.dsn ? tunnelFor(base.dsn) : undefined;
  return {
    ...base,
    enabled: base.enabled && tunnel !== undefined,
    tunnel,
    // Туннель на нашем домене: без credentials браузер не отправит cookie сессии в Sentry.
    transportOptions: { fetchOptions: { credentials: "omit" as const } },
    // Трассировка выключена; без BrowserTracing в заголовке конверта нет имени транзакции (URL).
    integrations: (defaults: Integration[]): Integration[] =>
      defaults.filter((integration) => integration.name !== "BrowserTracing"),
  };
}
