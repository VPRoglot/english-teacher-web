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

/** Mutator для orval: cookie того же origin, JSON, ошибки → ApiError. */
export async function apiFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network_error", "Нет соединения с сервером");
  }

  const requestId = response.headers.get("X-Request-ID");
  if (response.status === 204) return undefined as T;

  const body = await readJson(response);
  if (response.ok) return body as T;

  if (isErrorBody(body)) {
    const { code, message, details } = body.error;
    throw new ApiError(response.status, code, message, details ?? {}, requestId);
  }
  throw new ApiError(
    response.status,
    "unknown_error",
    `Сервер вернул ошибку ${response.status}`,
    {},
    requestId,
  );
}
