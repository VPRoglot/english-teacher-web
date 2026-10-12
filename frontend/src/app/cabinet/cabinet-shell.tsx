"use client";

import { useRouter } from "next/navigation";
import { Suspense, useEffect, type ReactNode } from "react";

import { useGetMe } from "@/api/generated/endpoints/auth/auth";
import type { MeResponse } from "@/api/generated/model";
import { AppHeader, type NavItem } from "@/components/app-header";
import { errorMessage } from "@/lib/form-errors";

import { withChild } from "./child-link";
import { ChildSwitcher } from "./child-switcher";
import { useSelectedChild } from "./use-selected-child";

function Skeleton() {
  return (
    <div role="status" aria-label="Загрузка" className="flex flex-1 flex-col">
      <div className="h-14 border-b" />
      <div className="mx-auto w-full max-w-5xl animate-pulse space-y-4 p-6">
        <div className="h-8 w-64 rounded-lg bg-muted" />
        <div className="h-32 rounded-xl bg-muted" />
      </div>
    </div>
  );
}

function CabinetHeader({ me, childId }: { me: MeResponse; childId: string | null }) {
  const nav: NavItem[] = [
    { href: withChild("/cabinet", childId), label: "Главная" },
    { href: withChild("/cabinet/calendar", childId), label: "Календарь" },
    ...(me.role === "parent" ? [{ href: "/cabinet/children", label: "Дети" }] : []),
    { href: "/cabinet/settings", label: "Настройки" },
  ];
  return <AppHeader title="Кабинет" nav={nav} me={me} actions={<ChildSwitcher />} />;
}

/** Шапка, в которой «Главная» и «Календарь» сохраняют выбранного ребёнка (`?child=`). */
function SelectedChildHeader({ me }: { me: MeResponse }) {
  const { childId } = useSelectedChild();
  return <CabinetHeader me={me} childId={childId} />;
}

export function CabinetShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const me = useGetMe();
  const role = me.data?.role;

  useEffect(() => {
    if (role === "tutor") router.replace("/admin");
  }, [role, router]);

  if (me.error && !me.data) {
    return (
      <main className="flex flex-1 items-center justify-center p-6">
        <p className="text-sm text-muted-foreground">{errorMessage(me.error)}</p>
      </main>
    );
  }
  if (!me.data || role === "tutor") return <Skeleton />;

  return (
    <div className="flex flex-1 flex-col">
      {/* Пока `useSearchParams` ждёт клиента, шапка рисуется без выбранного ребёнка. */}
      <Suspense fallback={<CabinetHeader me={me.data} childId={null} />}>
        <SelectedChildHeader me={me.data} />
      </Suspense>
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-6">{children}</main>
    </div>
  );
}
