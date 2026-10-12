import type { Metadata } from "next";
import { Suspense } from "react";

import { AdminCalendar } from "./admin-calendar";

export const metadata: Metadata = { title: "Календарь" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function CalendarPage() {
  return (
    <Suspense>
      <AdminCalendar />
    </Suspense>
  );
}
