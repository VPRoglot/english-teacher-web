import type { Metadata } from "next";
import { Suspense } from "react";

import { FamilyDetail } from "./family-detail";

export const metadata: Metadata = { title: "Семья" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function FamilyPage() {
  return (
    <Suspense>
      <FamilyDetail />
    </Suspense>
  );
}
