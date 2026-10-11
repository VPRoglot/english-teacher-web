import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Грубая защита маршрутов: без cookie `session` закрытые разделы ведут на /login.
 * Валидность сессии проверяет backend (401 → редирект на клиенте), здесь только быстрый отсев.
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has("session")) return NextResponse.next();
  const { pathname, search } = request.nextUrl;
  return NextResponse.redirect(
    new URL("/login?next=" + encodeURIComponent(pathname + search), request.url),
  );
}

export const config = {
  matcher: ["/cabinet/:path*", "/admin/:path*"],
};
