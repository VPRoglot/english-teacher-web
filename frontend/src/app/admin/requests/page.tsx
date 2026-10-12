import type { Metadata } from "next";
import { Suspense } from "react";

import { RequestsQueue } from "./requests-queue";

export const metadata: Metadata = { title: "Запросы" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function RequestsPage() {
  return (
    <Suspense>
      <RequestsQueue />
    </Suspense>
  );
}
