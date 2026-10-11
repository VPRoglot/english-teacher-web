import { useQueryClient } from "@tanstack/react-query";

import { getGetLeadQueryKey } from "@/api/generated/endpoints/admin/admin";

/** Перечитывает карточку заявки после мутации. */
export function useRefreshLead(leadId: string): () => Promise<void> {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: getGetLeadQueryKey(leadId) });
}
