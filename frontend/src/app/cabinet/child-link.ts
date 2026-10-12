import { CHILD_PARAM } from "./use-selected-child";

/** Адрес с `?child=<id>`, если ребёнок выбран; иначе адрес как есть. */
export function withChild(href: string, childId: string | null): string {
  return childId ? `${href}?${CHILD_PARAM}=${encodeURIComponent(childId)}` : href;
}
