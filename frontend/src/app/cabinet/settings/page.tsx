import type { Metadata } from "next";

import { ChangePassword } from "./change-password";

export const metadata: Metadata = { title: "Настройки" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function SettingsPage() {
  return <ChangePassword />;
}
