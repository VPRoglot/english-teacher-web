import type { Metadata } from "next";
import { Suspense } from "react";

import { SiteEditor } from "./site-editor";

export const metadata: Metadata = { title: "Сайт" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function SitePage() {
  return (
    <Suspense>
      <SiteEditor />
    </Suspense>
  );
}
