import type { LeadHistoryItem } from "@/api/generated/model";
import { formatDateTime } from "@/lib/datetime";
import { LEAD_STATUS_LABELS } from "@/lib/lead-format";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

function describe(item: LeadHistoryItem, timeZone: string): string {
  const change =
    item.from_status === null
      ? "Заявка получена"
      : `${LEAD_STATUS_LABELS[item.from_status]} → ${LEAD_STATUS_LABELS[item.to_status]}`;
  const parts = [formatDateTime(item.changed_at, timeZone), change];
  if (item.comment) parts.push(item.comment);
  return parts.join(" · ");
}

export function LeadHistory({ history }: { history: LeadHistoryItem[] }) {
  const timeZone = useTutorTimeZone("admin");
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">История</h2>
      <ol className="flex flex-col gap-1 text-sm">
        {history.map((item) => (
          <li key={`${item.changed_at}-${item.to_status}`} className="whitespace-pre-line">
            {describe(item, timeZone)}
          </li>
        ))}
      </ol>
    </section>
  );
}
