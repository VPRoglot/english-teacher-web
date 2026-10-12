"use client";

import { Suspense } from "react";

import { useGetMe } from "@/api/generated/endpoints/auth/auth";
import type { ChildSummary } from "@/api/generated/model";
import { NATIVE_SELECT_CLASS } from "@/components/native-select";
import { cn } from "@/lib/utils";

import { useSelectedChild } from "./use-selected-child";

function ChildSelect({ options }: { options: ChildSummary[] }) {
  const { childId, setChildId } = useSelectedChild();
  return (
    <select
      aria-label="Ребёнок"
      className={cn(NATIVE_SELECT_CLASS, "w-auto")}
      value={childId ?? ""}
      onChange={(event) => setChildId(event.target.value || null)}
    >
      <option value="">Все дети</option>
      {options.map((child) => (
        <option key={child.id} value={child.id}>
          {child.full_name}
        </option>
      ))}
    </select>
  );
}

/**
 * Переключатель ребёнка для родителя с двумя и более детьми: пишет выбор в `?child=`.
 * Остальным ничего не рисует. `useSearchParams` живёт во внутреннем компоненте под `Suspense`.
 */
export function ChildSwitcher() {
  const me = useGetMe();
  if (me.data?.role !== "parent" || me.data.children.length < 2) return null;
  return (
    <Suspense>
      <ChildSelect options={me.data.children} />
    </Suspense>
  );
}
