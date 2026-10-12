import { useQueryClient } from "@tanstack/react-query";

import {
  getGetDashboardQueryKey,
  getGetLeadQueryKey,
  getListLeadsQueryKey,
} from "@/api/generated/endpoints/admin/admin";

/**
 * Перечитывает карточку заявки, список заявок (статус виден и там) и дашборд (новые заявки)
 * после мутации.
 */
export function useRefreshLead(leadId: string): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    // Без параметров ключ списка — префикс всех его вариантов (фильтр, поиск, страница).
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: getGetLeadQueryKey(leadId) }),
      queryClient.invalidateQueries({ queryKey: getListLeadsQueryKey() }),
      queryClient.invalidateQueries({ queryKey: getGetDashboardQueryKey() }),
    ]);
  };
}
