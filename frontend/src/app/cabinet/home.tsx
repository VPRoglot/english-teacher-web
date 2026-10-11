"use client";

import { useGetMe } from "@/api/generated/endpoints/auth/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function Home() {
  const me = useGetMe().data;
  if (!me) return null;

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Здравствуйте, {me.display_name}!</h1>
      {me.role === "parent" && (
        <Card>
          <CardHeader>
            <CardTitle>Дети</CardTitle>
          </CardHeader>
          <CardContent>
            {me.children.length === 0 ? (
              <p className="text-sm text-muted-foreground">Детей пока нет.</p>
            ) : (
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {me.children.map((child) => (
                  <li key={child.id}>{child.full_name}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Расписание</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Расписание занятий появится здесь в ближайшее время
          </p>
        </CardContent>
      </Card>
    </>
  );
}
