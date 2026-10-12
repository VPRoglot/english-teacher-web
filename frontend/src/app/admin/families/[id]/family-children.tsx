"use client";

import { useState } from "react";
import { toast } from "sonner";

import { useUpdateChild } from "@/api/generated/endpoints/admin/admin";
import type { ChildDetail, FamilyDetail } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/form-errors";

import { ChildAccountDialog } from "./child-account-dialog";
import { ChildFormDialog } from "./child-form-dialog";
import { ChildSeries } from "./child-series";
import { ResetLinkButton } from "./reset-link-button";
import { useRefreshFamily } from "./use-refresh-family";

function ChildCard({ child, familyId }: { child: ChildDetail; familyId: string }) {
  const refresh = useRefreshFamily(familyId);
  const updateChild = useUpdateChild();
  const archived = child.archived_at !== null;
  const [confirmOpen, setConfirmOpen] = useState(false);

  function restore() {
    updateChild.mutate(
      { childId: child.id, data: { archived: false } },
      {
        onSuccess: async () => {
          toast.success("Ребёнок возвращён из архива");
          await refresh();
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  }

  async function archive() {
    await updateChild.mutateAsync({ childId: child.id, data: { archived: true } });
    toast.success("Ребёнок отправлен в архив");
    await refresh();
  }

  return (
    <Card className={cn(archived && "opacity-70")}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {child.full_name}
          {archived && <Badge variant="secondary">В архиве</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1 text-sm text-muted-foreground">
          <p>{`Год рождения: ${child.birth_year ?? "не указан"}`}</p>
          <p>{`Уровень: ${child.english_level ?? "не указан"}`}</p>
          <p>
            <span>Ссылка на занятие: </span>
            {child.default_meeting_url ? (
              <a
                href={child.default_meeting_url}
                target="_blank"
                rel="noopener noreferrer"
                className="break-all text-foreground underline underline-offset-2"
              >
                {child.default_meeting_url}
              </a>
            ) : (
              <span>не указана</span>
            )}
          </p>
          <p>{child.account ? `Логин: ${child.account.username}` : "Логин не выдан"}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ChildFormDialog familyId={familyId} child={child} />
          <ChildAccountDialog familyId={familyId} child={child} />
          {child.account && (
            <ResetLinkButton userId={child.account.user_id} ownerName={child.full_name} />
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label={archived ? "Вернуть ребёнка" : "В архив ребёнка"}
            disabled={updateChild.isPending}
            onClick={() => (archived ? restore() : setConfirmOpen(true))}
          >
            {archived ? "Вернуть" : "В архив"}
          </Button>
          <ConfirmDialog
            open={confirmOpen}
            onOpenChange={setConfirmOpen}
            title="Отправить ребёнка в архив?"
            description="Регулярные занятия будут завершены, будущие занятия удалены. Вернуть ребёнка можно в любой момент, но расписание не восстановится."
            confirmLabel="Да, в архив"
            onConfirm={archive}
          />
        </div>
        {!archived && <ChildSeries child={child} />}
      </CardContent>
    </Card>
  );
}

export function FamilyChildren({ family }: { family: FamilyDetail }) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Дети</h2>
        {family.archived_at === null && <ChildFormDialog familyId={family.id} />}
      </div>
      {family.children.length === 0 ? (
        <p className="text-sm text-muted-foreground">Детей пока нет.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {family.children.map((child) => (
            <ChildCard key={child.id} child={child} familyId={family.id} />
          ))}
        </div>
      )}
    </section>
  );
}
