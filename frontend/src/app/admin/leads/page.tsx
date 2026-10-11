import type { Metadata } from "next";
import { Suspense } from "react";

import { LeadsList } from "./leads-list";

export const metadata: Metadata = { title: "Заявки" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function LeadsPage() {
  return (
    <Suspense>
      <LeadsList />
    </Suspense>
  );
}
