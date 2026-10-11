"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useLogout } from "@/api/generated/endpoints/auth/auth";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/form-errors";

export function LogoutButton() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const logout = useLogout();

  function onClick() {
    logout.mutate(undefined, {
      onSuccess: () => {
        queryClient.clear();
        router.replace("/login");
      },
      onError: (error) => toast.error(errorMessage(error)),
    });
  }

  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={logout.isPending}>
      {logout.isPending ? "Выходим…" : "Выйти"}
    </Button>
  );
}
