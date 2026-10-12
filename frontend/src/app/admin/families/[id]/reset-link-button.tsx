"use client";

import { useState } from "react";
import { toast } from "sonner";

import { useCreateResetLink } from "@/api/generated/endpoints/admin/admin";
import type { LinkResponse } from "@/api/generated/model";
import { CopyLinkCard } from "@/components/copy-link-card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errorMessage } from "@/lib/form-errors";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

/** Выпускает ссылку для смены пароля пользователя и показывает её в диалоге для копирования. */
export function ResetLinkButton({ userId, ownerName }: { userId: string; ownerName: string }) {
  const timeZone = useTutorTimeZone("admin");
  const [link, setLink] = useState<LinkResponse | null>(null);
  const createLink = useCreateResetLink();

  function issue() {
    createLink.mutate(
      { userId },
      { onSuccess: setLink, onError: (error) => toast.error(errorMessage(error)) },
    );
  }

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={issue} disabled={createLink.isPending}>
        Ссылка для смены пароля
      </Button>
      <Dialog open={link !== null} onOpenChange={(open) => !open && setLink(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Смена пароля: {ownerName}</DialogTitle>
          </DialogHeader>
          {link && (
            <CopyLinkCard
              url={link.url}
              expiresAt={link.expires_at}
              timeZone={timeZone}
              title="Ссылка для смены пароля"
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
