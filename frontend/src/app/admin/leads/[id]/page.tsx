import type { Metadata } from "next";
import { Suspense } from "react";

import { LeadCard } from "./lead-card";

export const metadata: Metadata = { title: "Заявка" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function LeadPage() {
  return (
    <Suspense>
      <LeadCard />
    </Suspense>
  );
}
