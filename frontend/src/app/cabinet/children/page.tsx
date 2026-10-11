import type { Metadata } from "next";

import { ChildrenAccounts } from "./children-accounts";

export const metadata: Metadata = { title: "Дети" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function ChildrenPage() {
  return <ChildrenAccounts />;
}
