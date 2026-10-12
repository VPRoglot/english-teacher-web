"use client";

import { keepPreviousData } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useListLeads } from "@/api/generated/endpoints/admin/admin";
import type { LeadListItem, LeadStatus } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/datetime";
import { errorMessage } from "@/lib/form-errors";
import {
  CONTACT_METHOD_LABELS,
  LEAD_STATUS_BADGE_VARIANTS,
  LEAD_STATUS_LABELS,
  leadContactHref,
} from "@/lib/lead-format";
import { useTutorTimeZone } from "@/lib/use-tutor-time-zone";

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;
const ALL_STATUSES = "all";

const STATUS_FILTER_LABELS: Record<string, string> = {
  [ALL_STATUSES]: "Все",
  ...LEAD_STATUS_LABELS,
};

type Filters = { status: LeadStatus | null; q: string; page: number };

function isLeadStatus(value: string | null): value is LeadStatus {
  return value !== null && Object.hasOwn(LEAD_STATUS_LABELS, value);
}

function parsePage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page >= 1 ? page : 1;
}

function LeadRow({ lead, timeZone }: { lead: LeadListItem; timeZone: string }) {
  return (
    <TableRow className="relative">
      <TableCell className="whitespace-nowrap">{formatDateTime(lead.created_at, timeZone)}</TableCell>
      <TableCell className="font-medium">
        <Link
          href={`/admin/leads/${lead.id}`}
          className="before:absolute before:inset-0 hover:underline"
        >
          {lead.parent_name}
        </Link>
      </TableCell>
      <TableCell>{`${lead.child_name}, ${lead.child_age}`}</TableCell>
      <TableCell>
        {/* Ссылка контакта поверх растянутой ссылки строки, чтобы клик по ней не открывал заявку. */}
        <a href={leadContactHref(lead)} className="relative hover:underline">
          {`${CONTACT_METHOD_LABELS[lead.contact_method]} · ${lead.phone}`}
        </a>
      </TableCell>
      <TableCell>
        <Badge variant={LEAD_STATUS_BADGE_VARIANTS[lead.status]}>{LEAD_STATUS_LABELS[lead.status]}</Badge>
      </TableCell>
    </TableRow>
  );
}

export function LeadsList() {
  const router = useRouter();
  const pathname = usePathname();
  const currentQuery = useSearchParams().toString();
  const timeZone = useTutorTimeZone("admin");

  // Источник правды для запроса — состояние; адрес страницы только отражает его (и задаёт начальные значения).
  const [initial] = useState(() => new URLSearchParams(currentQuery));
  const [input, setInput] = useState(initial.get("q") ?? "");
  const [{ status, q, page }, setFilters] = useState<Filters>(() => {
    const initialStatus = initial.get("status");
    return {
      status: isLeadStatus(initialStatus) ? initialStatus : null,
      q: input.trim(),
      page: parsePage(initial.get("page")),
    };
  });

  useEffect(() => {
    const timer = setTimeout(() => {
      const next = input.trim();
      setFilters((prev) => (prev.q === next ? prev : { ...prev, q: next, page: 1 }));
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    if (page > 1) params.set("page", String(page));
    const next = params.toString();
    if (next !== currentQuery) router.replace(next ? `${pathname}?${next}` : pathname);
  }, [status, q, page, currentQuery, pathname, router]);

  const leads = useListLeads(
    { status: status ?? undefined, q: q || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE },
    { query: { placeholderData: keepPreviousData } },
  );

  const total = leads.data?.total ?? 0;
  const from = (page - 1) * PAGE_SIZE + 1;
  const to = (page - 1) * PAGE_SIZE + (leads.data?.items.length ?? 0);

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Заявки</h1>
      <div className="flex flex-wrap items-center gap-4">
        <Select
          items={STATUS_FILTER_LABELS}
          value={status ?? ALL_STATUSES}
          onValueChange={(value) =>
            setFilters((prev) => ({
              ...prev,
              status: isLeadStatus(value) ? value : null,
              page: 1,
            }))
          }
        >
          <SelectTrigger aria-label="Статус" className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(STATUS_FILTER_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="search"
          aria-label="Поиск"
          placeholder="Родитель, ребёнок, телефон или ник"
          className="max-w-xs"
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
      </div>
      {leads.error ? (
        <p className="text-sm text-muted-foreground">{errorMessage(leads.error)}</p>
      ) : !leads.data ? null : leads.data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {q || status ? "Ничего не найдено" : "Заявок пока нет"}
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Дата</TableHead>
              <TableHead>Родитель</TableHead>
              <TableHead>Ребёнок, возраст</TableHead>
              <TableHead>Контакт</TableHead>
              <TableHead>Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {leads.data.items.map((lead) => (
              <LeadRow key={lead.id} lead={lead} timeZone={timeZone} />
            ))}
          </TableBody>
        </Table>
      )}
      {leads.data && (total > PAGE_SIZE || page > 1) && (
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-muted-foreground">
            {leads.data.items.length > 0 ? `${from}–${to} из ${total}` : `Всего: ${total}`}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() => setFilters((prev) => ({ ...prev, page: prev.page - 1 }))}
            >
              Назад
            </Button>
            <Button
              variant="outline"
              disabled={page * PAGE_SIZE >= total}
              onClick={() => setFilters((prev) => ({ ...prev, page: prev.page + 1 }))}
            >
              Дальше
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
