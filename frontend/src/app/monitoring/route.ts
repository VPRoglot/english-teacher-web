import { envelopeUrl, parseDsn, sameDsn } from "@/lib/sentry-options";

/** Конверт ошибки — единицы килобайт; больше 1 МБ из браузера не принимаем. */
const MAX_ENVELOPE_BYTES = 1024 * 1024;
const UPSTREAM_TIMEOUT_MS = 5000;
// Ответные заголовки Sentry, по которым SDK в браузере соблюдает лимиты.
const PASSED_HEADERS = ["retry-after", "x-sentry-rate-limits"];

function errorResponse(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message } }, { status });
}

class TooLargeError extends Error {}

/** Читает тело потоком и обрывает чтение, как только оно превысило лимит. */
async function readBody(request: Request): Promise<Uint8Array<ArrayBuffer>> {
  const declared = Number(request.headers.get("content-length"));
  if (declared > MAX_ENVELOPE_BYTES) throw new TooLargeError();
  if (!request.body) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_ENVELOPE_BYTES) {
      await reader.cancel();
      throw new TooLargeError();
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

/** DSN из заголовка конверта (первая строка, JSON); undefined — заголовок некорректен. */
function envelopeDsn(body: Uint8Array): string | undefined {
  const newline = body.indexOf(0x0a);
  const firstLine = new TextDecoder().decode(newline === -1 ? body : body.subarray(0, newline));
  try {
    const header: unknown = JSON.parse(firstLine);
    if (header !== null && typeof header === "object" && "dsn" in header) {
      return typeof header.dsn === "string" ? header.dsn : undefined;
    }
  } catch {
    // некорректный JSON — ниже ответ 400
  }
  return undefined;
}

/**
 * Туннель браузерного Sentry: CSP разрешает браузеру только свой домен (`connect-src 'self'`),
 * поэтому конверты идут сюда, а сервер пересылает их в Sentry/GlitchTip. Пересылаются только
 * конверты нашего проекта (DSN совпадает с NEXT_PUBLIC_SENTRY_DSN) — не открытый релей.
 */
export async function POST(request: Request): Promise<Response> {
  const configured = parseDsn(process.env.NEXT_PUBLIC_SENTRY_DSN);
  if (!configured) return errorResponse(404, "not_found", "Не найдено");

  let body: Uint8Array<ArrayBuffer>;
  try {
    body = await readBody(request);
  } catch (error) {
    if (error instanceof TooLargeError) {
      return errorResponse(413, "envelope_too_large", "Слишком большой конверт");
    }
    throw error;
  }

  const raw = envelopeDsn(body);
  if (raw === undefined) {
    return errorResponse(400, "invalid_envelope", "Некорректный заголовок конверта");
  }
  const dsn = parseDsn(raw);
  if (!dsn || !sameDsn(dsn, configured)) {
    return errorResponse(403, "foreign_dsn", "Чужой DSN");
  }

  let upstream: Response;
  try {
    upstream = await fetch(envelopeUrl(configured), {
      method: "POST",
      body,
      headers: {
        "Content-Type": "application/x-sentry-envelope",
        // Явная авторизация ключом проекта (публичным): так конверт примут и Sentry, и GlitchTip.
        "X-Sentry-Auth": `Sentry sentry_version=7, sentry_key=${configured.publicKey}, sentry_client=web-tunnel`,
      },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch {
    return errorResponse(502, "upstream_unavailable", "Sentry недоступен");
  }
  const headers = new Headers();
  for (const name of PASSED_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(null, { status: upstream.status, headers });
}
