import type { Metadata } from "next";
import { Suspense } from "react";

import { CabinetLesson } from "./cabinet-lesson";

export const metadata: Metadata = { title: "Занятие" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function CabinetLessonPage() {
  return (
    <Suspense>
      <CabinetLesson />
    </Suspense>
  );
}
