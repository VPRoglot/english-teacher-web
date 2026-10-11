import type { Metadata } from "next";
import { Suspense } from "react";

import { FamiliesList } from "./families-list";

export const metadata: Metadata = { title: "Семьи" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function FamiliesPage() {
  return (
    <Suspense>
      <FamiliesList />
    </Suspense>
  );
}
