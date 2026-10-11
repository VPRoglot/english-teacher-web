"use client";

import { useState } from "react";
import { toast } from "sonner";

import { useUpdateUserStatus } from "@/api/generated/endpoints/admin/admin";
import type { FamilyDetail, ParentDetail } from "@/api/generated/model";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/form-errors";
import { formatMoscow } from "@/lib/format";

import { ResetLinkButton } from "./reset-link-button";
import { useRefreshFamily } from "./use-refresh-family";

function ParentActions({ parent, familyId }: { parent: ParentDetail; familyId: string }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const refresh = useRefreshFamily(familyId);
  const updateStatus = useUpdateUserStatus();

  async function setActive(isActive: boolean) {
    await updateStatus.mutateAsync({ userId: parent.user_id, data: { is_active: isActive } });
    toast.success(isActive ? "Родитель разблокирован" : "Родитель заблокирован");
    await refresh();
  }

  return (
    <div className="flex flex-wrap justify-end gap-2">
      <ResetLinkButton userId={parent.user_id} ownerName={parent.full_name} />
      {parent.is_active ? (
        <Button type="button" variant="destructive" size="sm" onClick={() => setConfirmOpen(true)}>
          Заблокировать
        </Button>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={updateStatus.isPending}
          onClick={() => setActive(true).catch((error) => toast.error(errorMessage(error)))}
        >
          Разблокировать
        </Button>
      )}
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Заблокировать родителя?"
        description={`${parent.full_name} не сможет войти в кабинет, пока вы не разблокируете доступ.`}
        confirmLabel="Да, заблокировать"
        onConfirm={() => setActive(false)}
      />
    </div>
  );
}

export function FamilyParents({ family }: { family: FamilyDetail }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">Родители</h2>
      {family.parents.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {family.pending_invitation
            ? "Родитель ещё не принял приглашение."
            : "Создайте ссылку-приглашение и отправьте её родителю"}
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ФИО</TableHead>
              <TableHead>Телефон</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Последний вход</TableHead>
              <TableHead>Статус</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {family.parents.map((parent) => (
              <TableRow key={parent.user_id}>
                <TableCell className="font-medium">{parent.full_name}</TableCell>
                <TableCell>{parent.phone}</TableCell>
                <TableCell>{parent.email}</TableCell>
                <TableCell>{parent.last_login_at ? formatMoscow(parent.last_login_at) : "—"}</TableCell>
                <TableCell>
                  <Badge variant={parent.is_active ? "secondary" : "destructive"}>
                    {parent.is_active ? "Активен" : "Заблокирован"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <ParentActions parent={parent} familyId={family.id} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </section>
  );
}
