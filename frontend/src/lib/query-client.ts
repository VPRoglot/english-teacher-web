import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { ApiError } from "./api-fetch";

/** Клиентские ошибки (4xx) не лечатся повтором; остальные — один повтор. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

/** `onUnauthenticated` вызывается при 401, если у запроса нет `meta.skipAuthRedirect`. */
export function makeQueryClient(onUnauthenticated: () => void): QueryClient {
  const handleError = (error: unknown, meta: Record<string, unknown> | undefined) => {
    if (error instanceof ApiError && error.status === 401 && !meta?.skipAuthRedirect) {
      onUnauthenticated();
    }
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError: (error, query) => handleError(error, query.meta) }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => handleError(error, mutation.meta),
    }),
    defaultOptions: {
      queries: { staleTime: 30_000, retry: shouldRetry },
      mutations: { retry: false },
    },
  });
}
