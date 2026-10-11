/** Ошибка API в едином формате backend: `{"error": {"code", "message", "details"}}`. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

type ErrorBody = { error: { code: string; message: string; details?: Record<string, unknown> } };

function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const CSRF_URL = "/api/auth/csrf";
const CSRF_COOKIE = "csrf_token";
const CSRF_HEADER = "X-CSRF-Token";

function readCsrfCookie(): string | null {
  for (const part of document.cookie.split(";")) {
    const [name, ...value] = part.trim().split("=");
    if (name === CSRF_COOKIE) return decodeURIComponent(value.join("="));
  }
  return null;
}

function isAbort(error: unknown, init: RequestInit): boolean {
  return (
    init.signal?.aborted === true || (error as { name?: unknown } | null)?.name === "AbortError"
  );
}

/** fetch с единым разбором сбоев: отмена пробрасывается как есть, остальное → network_error. */
async function send(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, { ...init, credentials: "same-origin" });
  } catch (error) {
    if (isAbort(error, init)) throw error;
    throw new ApiError(0, "network_error", "Нет соединения с сервером");
  }
}

function unknownError(response: Response, requestId: string | null): ApiError {
  return new ApiError(
    response.status,
    "unknown_error",
    `Сервер вернул ошибку ${response.status}`,
    {},
    requestId,
  );
}

/** Запрашивает новый CSRF-токен: backend выставляет cookie `csrf_token`. */
async function refreshCsrfToken(signal: AbortSignal | null | undefined): Promise<string | null> {
  const response = await send(CSRF_URL, { method: "GET", signal });
  if (!response.ok) throw unknownError(response, response.headers.get("X-Request-ID"));
  return readCsrfCookie();
}

async function request<T>(
  url: string,
  init: RequestInit,
  retryOnCsrfFailure: boolean,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  const method = (init.method ?? "GET").toUpperCase();
  if (!SAFE_METHODS.has(method)) {
    // Без токена сервер ответит csrf_failed — это обработает единственный повтор ниже.
    const token = readCsrfCookie() ?? (await refreshCsrfToken(init.signal));
    if (token !== null) headers.set(CSRF_HEADER, token);
  }

  const response = await send(url, { ...init, headers });
  const requestId = response.headers.get("X-Request-ID");
  if (response.status === 204) return undefined as T;

  const body = await readJson(response);
  if (response.ok) return body as T;

  if (isErrorBody(body)) {
    const { code, message, details } = body.error;
    if (retryOnCsrfFailure && response.status === 403 && code === "csrf_failed") {
      await refreshCsrfToken(init.signal);
      return request<T>(url, init, false);
    }
    throw new ApiError(response.status, code, message, details ?? {}, requestId);
  }
  throw unknownError(response, requestId);
}

/** Mutator для orval: cookie того же origin, JSON, CSRF для небезопасных методов, ошибки → ApiError. */
export function apiFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
  return request<T>(url, init, true);
}

/** orval подставляет эти типы в `TError`/`TBody` сгенерированных хуков. */
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- сигнатура задана orval
export type ErrorType<E> = ApiError;
export type BodyType<B> = B;
