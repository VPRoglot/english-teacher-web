import type { Metadata } from "next";

import { CabinetShell } from "./cabinet-shell";

export const metadata: Metadata = {
  title: "Кабинет",
  robots: { index: false, follow: false },
};

export default function CabinetLayout({ children }: LayoutProps<"/cabinet">) {
  return <CabinetShell>{children}</CabinetShell>;
}
