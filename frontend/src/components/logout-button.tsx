"use client";

import { useQueryClient } from "@tanstack/react-query";

import { useLogout } from "@/api/generated/endpoints/auth/auth";
import { Button } from "@/components/ui/button";

export function LogoutButton() {
  const queryClient = useQueryClient();
  const logout = useLogout();

  function onClick() {
    logout.mutate(undefined, {
      // И при ошибке: на /login сессия перепроверяется, и если она жива — вернёт обратно.
      onSettled: () => {
        queryClient.clear();
        // Полная перезагрузка, а не router.replace: с cacheComponents посещённые страницы
        // остаются скрытыми в <Activity> — с данными прежнего пользователя и формой входа,
        // где ещё лежат его логин и пароль.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign("/login");
      },
    });
  }

  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={logout.isPending}>
      {logout.isPending ? "Выходим…" : "Выйти"}
    </Button>
  );
}
