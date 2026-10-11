import type { Metadata } from "next";

import { AdminShell } from "./admin-shell";

export const metadata: Metadata = {
  title: "Админка",
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return <AdminShell>{children}</AdminShell>;
}
