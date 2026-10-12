import type { Metadata } from "next";

import { Dashboard } from "./dashboard";

export const metadata: Metadata = { title: "Обзор" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function AdminPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Обзор</h1>
      <Dashboard />
    </>
  );
}
