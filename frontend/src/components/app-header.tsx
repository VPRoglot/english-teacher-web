"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { MeResponse } from "@/api/generated/model";
import { LogoutButton } from "@/components/logout-button";
import { cn } from "@/lib/utils";

export type NavItem = { href: string; label: string };

/** Активна ссылка с самым длинным совпавшим префиксом: «/cabinet» не подсвечивается на «/cabinet/settings». */
function activeHref(pathname: string, nav: readonly NavItem[]): string | null {
  const matches = nav.filter(({ href }) => pathname === href || pathname.startsWith(`${href}/`));
  matches.sort((a, b) => b.href.length - a.href.length);
  return matches[0]?.href ?? null;
}

export function AppHeader({ title, nav, me }: { title: string; nav: NavItem[]; me: MeResponse }) {
  const active = activeHref(usePathname(), nav);
  return (
    <header className="border-b">
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
        <span className="font-semibold">{title}</span>
        <nav aria-label="Основная навигация" className="flex flex-1 flex-wrap items-center gap-1">
          {nav.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              aria-current={href === active ? "page" : undefined}
              className={cn(
                "rounded-lg px-2.5 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground",
                href === active && "bg-muted font-medium text-foreground",
              )}
            >
              {label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{me.display_name}</span>
          <LogoutButton />
        </div>
      </div>
    </header>
  );
}
