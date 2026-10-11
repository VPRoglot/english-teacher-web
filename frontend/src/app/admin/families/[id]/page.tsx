import type { Metadata } from "next";
import { Suspense } from "react";

import { FamilyDetail } from "./family-detail";

export const metadata: Metadata = { title: "Семья" };

export default function FamilyPage() {
  return (
    <Suspense>
      <FamilyDetail />
    </Suspense>
  );
}
