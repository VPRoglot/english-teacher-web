import type { Metadata } from "next";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = { title: "Обзор" };

export default function AdminPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Обзор</h1>
      <Card>
        <CardHeader>
          <CardTitle>Скоро здесь будет больше</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-start gap-4">
          <p className="text-sm text-muted-foreground">
            Заявки, расписание и запросы на перенос появятся в следующих версиях.
          </p>
          <Link href="/admin/families" className={buttonVariants()}>
            Перейти к семьям
          </Link>
        </CardContent>
      </Card>
    </>
  );
}
