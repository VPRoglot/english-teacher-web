import type { Metadata } from "next";
import { Suspense } from "react";

import { ResetPassword } from "./reset-password";

export const metadata: Metadata = {
  title: "Смена пароля",
  robots: { index: false },
  // Токен в URL не должен утекать через заголовок Referer.
  referrer: "no-referrer",
};

export default function ResetPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <Suspense>
        <ResetPassword />
      </Suspense>
    </main>
  );
}
