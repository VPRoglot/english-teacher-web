import type { UserRole } from "@/api/generated/model";

export function homeFor(role: UserRole): "/admin" | "/cabinet" {
  return role === "tutor" ? "/admin" : "/cabinet";
}

/** Пропускает только локальный путь (`/...`): без `//`, `/\`, схемы и управляющих символов. */
export function safeNext(next: string | null): string | null {
  if (next === null || !next.startsWith("/")) return null;
  if (next.startsWith("//") || next.startsWith("/\\")) return null;
  if (/[\u0000-\u001f\u007f]/.test(next)) return null;
  return next;
}
