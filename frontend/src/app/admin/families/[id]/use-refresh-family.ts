import { useQueryClient } from "@tanstack/react-query";

import { getGetFamilyQueryKey } from "@/api/generated/endpoints/admin/admin";

/** Перечитывает карточку семьи после мутации. */
export function useRefreshFamily(familyId: string): () => Promise<void> {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: getGetFamilyQueryKey(familyId) });
}
