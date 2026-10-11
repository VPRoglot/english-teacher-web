import { useQueryClient } from "@tanstack/react-query";

import { getGetLeadQueryKey, getListLeadsQueryKey } from "@/api/generated/endpoints/admin/admin";

/** Перечитывает карточку заявки и список заявок (статус виден и там) после мутации. */
export function useRefreshLead(leadId: string): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    // Без параметров ключ списка — префикс всех его вариантов (фильтр, поиск, страница).
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: getGetLeadQueryKey(leadId) }),
      queryClient.invalidateQueries({ queryKey: getListLeadsQueryKey() }),
    ]);
  };
}
