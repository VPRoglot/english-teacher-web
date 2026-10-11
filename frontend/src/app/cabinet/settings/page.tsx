import type { Metadata } from "next";

import { ChangePassword } from "./change-password";

export const metadata: Metadata = { title: "Настройки" };

export default function SettingsPage() {
  return <ChangePassword />;
}
