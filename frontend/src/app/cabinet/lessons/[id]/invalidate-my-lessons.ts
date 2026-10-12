import type { QueryClient } from "@tanstack/react-query";

const MY_LESSONS_PREFIX = "/api/me/lessons";

/** После запроса или отзыва: карточка занятия и списки занятий кабинета (`/api/me/lessons…`) устарели. */
export function invalidateMyLessons(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({
    predicate: ({ queryKey }) =>
      typeof queryKey[0] === "string" && queryKey[0].startsWith(MY_LESSONS_PREFIX),
  });
}
