import type { Metadata } from "next";

import { ChildrenAccounts } from "./children-accounts";

export const metadata: Metadata = { title: "Дети" };

export default function ChildrenPage() {
  return <ChildrenAccounts />;
}
