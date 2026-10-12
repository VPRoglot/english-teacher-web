"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { useGetFamily, useUpdateFamily } from "@/api/generated/endpoints/admin/admin";
import type { FamilyDetail as FamilyDetailData } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/form-errors";
import { invalidateSchedule } from "@/lib/lesson-mutations";

import { EditFamilyDialog } from "./edit-family-dialog";
import { FamilyChildren } from "./family-children";
import { FamilyInvitation } from "./family-invitation";
import { FamilyParents } from "./family-parents";
import { useRefreshFamily } from "./use-refresh-family";

function ArchiveButton({ family }: { family: FamilyDetailData }) {
  const [open, setOpen] = useState(false);
  const refresh = useRefreshFamily(family.id);
  const queryClient = useQueryClient();
  const update = useUpdateFamily();
  const archived = family.archived_at !== null;

  async function toggle() {
    await update.mutateAsync({ familyId: family.id, data: { archived: !archived } });
    toast.success(archived ? "Семья возвращена из архива" : "Семья отправлена в архив");
    // Архив семьи завершает серии её детей: занятия, серии и дашборд устарели.
    if (!archived) invalidateSchedule(queryClient);
    await refresh();
  }

  return (
    <>
      <Button type="button" variant="outline" onClick={() => setOpen(true)}>
        {archived ? "Вернуть из архива" : "В архив"}
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={archived ? "Вернуть семью из архива?" : "Отправить семью в архив?"}
        description={
          archived
            ? "Семья снова появится в основном списке."
            : "Семья исчезнет из основного списка. Регулярные занятия будут завершены, будущие занятия удалены. Вернуть семью можно в любой момент, но расписание не восстановится."
        }
        confirmLabel={archived ? "Да, вернуть" : "Да, в архив"}
        onConfirm={toggle}
      />
    </>
  );
}

function Skeleton() {
  return (
    <div role="status" aria-label="Загрузка" className="animate-pulse space-y-4">
      <div className="h-8 w-64 rounded-lg bg-muted" />
      <div className="h-32 rounded-xl bg-muted" />
    </div>
  );
}

export function FamilyDetail() {
  const { id } = useParams<{ id: string }>();
  const family = useGetFamily(id);

  if (family.error && !family.data) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-muted-foreground">{errorMessage(family.error)}</p>
        <Link href="/admin/families" className="text-sm underline underline-offset-2">
          К списку семей
        </Link>
      </div>
    );
  }
  if (!family.data) return <Skeleton />;

  const data = family.data;
  return (
    <>
      <div className="flex flex-col gap-3">
        <Link
          href="/admin/families"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          Все семьи
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
              {data.archived_at && <Badge variant="secondary">В архиве</Badge>}
            </div>
            {data.tutor_comment && (
              <p className="text-sm whitespace-pre-line text-muted-foreground">{data.tutor_comment}</p>
            )}
          </div>
          <div className="flex gap-2">
            <EditFamilyDialog family={data} />
            <ArchiveButton family={data} />
          </div>
        </div>
      </div>
      <FamilyParents family={data} />
      <FamilyInvitation family={data} />
      <FamilyChildren family={data} />
    </>
  );
}
