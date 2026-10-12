import type { Metadata } from "next";
import { Suspense } from "react";

import { SettingsForm } from "./settings-form";

export const metadata: Metadata = { title: "Настройки" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function SettingsPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold">Настройки</h1>
      <Suspense>
        <SettingsForm />
      </Suspense>
    </>
  );
}
