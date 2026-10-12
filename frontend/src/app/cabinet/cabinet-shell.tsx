"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useGetMe } from "@/api/generated/endpoints/auth/auth";
import { AppHeader, type NavItem } from "@/components/app-header";
import { errorMessage } from "@/lib/form-errors";

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

  const nav: NavItem[] = [
    { href: "/cabinet", label: "Главная" },
    { href: "/cabinet/calendar", label: "Календарь" },
    ...(role === "parent" ? [{ href: "/cabinet/children", label: "Дети" }] : []),
    { href: "/cabinet/settings", label: "Настройки" },
  ];

  return (
    <div className="flex flex-1 flex-col">
      <AppHeader title="Кабинет" nav={nav} me={me.data} />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-6">{children}</main>
    </div>
  );
}
