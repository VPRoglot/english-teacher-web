import type { Metadata } from "next";
import { Suspense } from "react";

import { FamiliesList } from "./families-list";

export const metadata: Metadata = { title: "Семьи" };

export default function FamiliesPage() {
  return (
    <Suspense>
      <FamiliesList />
    </Suspense>
  );
}
