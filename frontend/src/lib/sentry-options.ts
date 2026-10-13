import type { Breadcrumb, BrowserOptions, ErrorEvent, getDefaultIntegrations } from "@sentry/nextjs";

// @sentry/core — транзитивная зависимость: типы берём через публичный API @sentry/nextjs.
type TransactionEvent = Parameters<NonNullable<BrowserOptions["beforeSendTransaction"]>>[0];
type Integration = ReturnType<typeof getDefaultIntegrations>[number];

/** Туннель браузерных событий: Route Handler `src/app/monitoring/route.ts`. */
export const SENTRY_TUNNEL_ROUTE = "/monitoring";

const MASK = "***";
// Те же правила, что `scrub_text` в backend/app/core/observability.py: одноразовые токены из
// ссылок приглашения и сброса пароля и токен Telegram-бота не должны попадать в Sentry.
const SECRET_PATTERNS: readonly RegExp[] = [
  /(\/(?:invite|reset|api\/auth\/invitations|api\/auth\/password-resets)\/)[^/?#\s"']+/g,
  /(api\.telegram\.org\/bot)[^/?#\s"']+/g,
];
const DROPPED_HEADERS = new Set([
  "cookie",
  "set-cookie",
  "authorization",
  "x-csrf-token",
  "x-forwarded-for",
  "x-real-ip",
]);
// Глубже Sentry всё равно не сериализует (normalizeDepth по умолчанию 3) — дальше заглушка.
const MAX_SCRUB_DEPTH = 10;
const TRUNCATED = "[Truncated]";
const CIRCULAR = "[Circular]";

export function scrubUrl(url: string): string {
  return SECRET_PATTERNS.reduce((text, pattern) => text.replace(pattern, `$1${MASK}`), url);
}

function isPlainObject(value: object): value is Record<string, unknown> {
  const proto: unknown = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/**
 * Копия с замаскированными строками. Рекурсия только в массивы и простые объекты: в breadcrumb'ах
 * console лежат живые аргументы (DOM-узлы, циклические структуры, геттеры) — их не обходим,
 * Sentry сериализует их сам. Циклы и слишком глубокие ветки заменяются заглушкой.
 */
function scrubDeep(value: unknown, seen: WeakSet<object> = new WeakSet(), depth = 0): unknown {
  if (typeof value === "string") return scrubUrl(value);
  if (value === null || typeof value !== "object") return value;
  if (!Array.isArray(value) && !isPlainObject(value)) return value;
  if (seen.has(value)) return CIRCULAR;
  if (depth >= MAX_SCRUB_DEPTH) return TRUNCATED;
  seen.add(value);
  const result = Array.isArray(value)
    ? value.map((item) => scrubDeep(item, seen, depth + 1))
    : Object.fromEntries(
        Object.entries(value).map(([key, item]) => [key, scrubDeep(item, seen, depth + 1)]),
      );
  seen.delete(value);
  return result;
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
 * Браузер: события идут только в туннель `/monitoring` на своём домене (CSP `connect-src 'self'`),
 * для любого DSN — sentry.io или GlitchTip. Ingest-хост браузер не вызывает никогда.
 */
export function browserSentryOptions(env: SentryEnv) {
  return {
    ...sentryOptions(env),
    tunnel: SENTRY_TUNNEL_ROUTE,
    // Туннель на нашем домене: без credentials браузер не отправит в него cookie сессии.
    transportOptions: { fetchOptions: { credentials: "omit" as const } },
    // Трассировка выключена; без BrowserTracing в заголовке конверта нет имени транзакции (URL).
    integrations: (defaults: Integration[]): Integration[] =>
      defaults.filter((integration) => integration.name !== "BrowserTracing"),
  };
}

export interface ParsedDsn {
  protocol: string;
  host: string;
  pathPrefix: string;
  projectId: string;
  publicKey: string;
}

/** Разбирает DSN `https://<key>@<host>[:port][/<prefix>]/<projectId>`; некорректный — undefined. */
export function parseDsn(dsn: string | undefined): ParsedDsn | undefined {
  if (!dsn) return undefined;
  let url: URL;
  try {
    url = new URL(dsn);
  } catch {
    return undefined;
  }
  const segments = url.pathname.split("/").filter(Boolean);
  const projectId = segments.pop();
  if (
    (url.protocol !== "https:" && url.protocol !== "http:") ||
    !url.username ||
    !projectId ||
    !/^\d+$/.test(projectId)
  ) {
    return undefined;
  }
  return {
    protocol: url.protocol,
    host: url.host,
    pathPrefix: segments.length ? `/${segments.join("/")}` : "",
    projectId,
    publicKey: url.username,
  };
}

export function sameDsn(a: ParsedDsn, b: ParsedDsn): boolean {
  return (
    a.protocol === b.protocol &&
    a.host === b.host &&
    a.pathPrefix === b.pathPrefix &&
    a.projectId === b.projectId &&
    a.publicKey === b.publicKey
  );
}

/** Адрес приёма конвертов проекта (Sentry и GlitchTip). */
export function envelopeUrl(dsn: ParsedDsn): string {
  return `${dsn.protocol}//${dsn.host}${dsn.pathPrefix}/api/${dsn.projectId}/envelope/`;
}
