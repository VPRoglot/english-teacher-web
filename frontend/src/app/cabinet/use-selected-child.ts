"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { useGetMe } from "@/api/generated/endpoints/auth/auth";

export const CHILD_PARAM = "child";

/**
 * Выбранный ребёнок кабинета: `?child=<id>` в адресе (так выбор переживает перезагрузку и ссылки).
 * Идентификатор не из `me.children` (чужой, устаревший, выдуманный) и любая роль, кроме родителя,
 * дают `null`, то есть «все дети». Использует `useSearchParams`, поэтому вызывается внутри `Suspense`.
 */
export function useSelectedChild(): {
  childId: string | null;
  setChildId: (id: string | null) => void;
} {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const me = useGetMe();

  const requested = searchParams.get(CHILD_PARAM);
  const childId =
    me.data?.role === "parent" && me.data.children.some((child) => child.id === requested)
      ? requested
      : null;

  const setChildId = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(searchParams.toString());
      if (id === null) next.delete(CHILD_PARAM);
      else next.set(CHILD_PARAM, id);
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : pathname);
    },
    [router, pathname, searchParams],
  );

  return { childId, setChildId };
}
