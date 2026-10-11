"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { makeQueryClient } from "@/lib/query-client";

const PUBLIC_PATH = /^\/(login|invite\/|reset\/)/;

function redirectToLogin() {
  const { pathname, search } = window.location;
  if (PUBLIC_PATH.test(pathname)) return;
  // Полная перезагрузка намеренна: сбрасывает кэш и состояние сессии, не только маршрут.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign("/login?next=" + encodeURIComponent(pathname + search));
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => makeQueryClient(redirectToLogin));
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
