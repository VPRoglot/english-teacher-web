import type { Metadata } from "next";

import { Home } from "./home";

export const metadata: Metadata = { title: "Главная" };

// Область целиком клиентская и за сессией: оболочка рендерит скелет до ответа /api/auth/me,
// поэтому проверка instant-навигации здесь невозможна и не нужна.
export const instant = false;

export default function CabinetPage() {
  return <Home />;
}
