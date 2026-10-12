import type { Metadata } from "next";
import { Suspense } from "react";

import { CabinetCalendar } from "./cabinet-calendar";

export const metadata: Metadata = { title: "Календарь" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function CabinetCalendarPage() {
  return (
    <Suspense>
      <CabinetCalendar />
    </Suspense>
  );
}
