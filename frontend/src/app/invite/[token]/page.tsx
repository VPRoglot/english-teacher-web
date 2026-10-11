import type { Metadata } from "next";
import { Suspense } from "react";

import { AcceptInvitation } from "./accept-invitation";

export const metadata: Metadata = {
  title: "Приглашение",
  robots: { index: false },
  // Токен в URL не должен утекать через заголовок Referer.
  referrer: "no-referrer",
};

export default function InvitePage() {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <Suspense>
        <AcceptInvitation />
      </Suspense>
    </main>
  );
}
