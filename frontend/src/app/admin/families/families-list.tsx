"use client";

import { keepPreviousData } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useListFamilies } from "@/api/generated/endpoints/admin/admin";
import type { FamilyListItem } from "@/api/generated/model";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/form-errors";

import { CreateFamilyDialog } from "./create-family-dialog";

const SEARCH_DEBOUNCE_MS = 300;

function FamilyRow({ family }: { family: FamilyListItem }) {
  return (
    <TableRow className="relative">
      <TableCell className="font-medium">
        <Link
          href={`/admin/families/${family.id}`}
          className="before:absolute before:inset-0 hover:underline"
        >
          {family.name}
        </Link>
        {family.archived_at && (
          <Badge variant="secondary" className="ml-2">
            В архиве
          </Badge>
        )}
      </TableCell>
      <TableCell>{family.parent_names.join(", ") || "—"}</TableCell>
      <TableCell>{family.children.map((child) => child.full_name).join(", ") || "—"}</TableCell>
    </TableRow>
  );
}

export function FamiliesList() {
  const router = useRouter();
  const pathname = usePathname();
  const currentQuery = useSearchParams().toString();

  // Источник правды для запроса — состояние; адрес страницы только отражает его (и задаёт начальные значения).
  const [initial] = useState(() => new URLSearchParams(currentQuery));
  const [input, setInput] = useState(initial.get("q") ?? "");
  const [q, setQ] = useState(input.trim());
  const [archived, setArchived] = useState(initial.get("archived") === "true");

  useEffect(() => {
    const timer = setTimeout(() => setQ(input.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [input]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (archived) params.set("archived", "true");
    const next = params.toString();
    if (next !== currentQuery) router.replace(next ? `${pathname}?${next}` : pathname);
  }, [q, archived, currentQuery, pathname, router]);

  const families = useListFamilies(
    { q: q || undefined, archived },
    { query: { placeholderData: keepPreviousData } },
  );

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Семьи</h1>
        <CreateFamilyDialog />
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <Input
          type="search"
          aria-label="Поиск"
          placeholder="Семья, родитель или ребёнок"
          className="max-w-xs"
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
        <div className="flex items-center gap-2">
          <Checkbox id="archived" checked={archived} onCheckedChange={setArchived} />
          <Label htmlFor="archived" className="font-normal">
            Архив
          </Label>
        </div>
      </div>
      {families.error ? (
        <p className="text-sm text-muted-foreground">{errorMessage(families.error)}</p>
      ) : !families.data ? null : families.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {q ? "Ничего не найдено." : archived ? "В архиве пока пусто." : "Семей пока нет."}
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Семья</TableHead>
              <TableHead>Родители</TableHead>
              <TableHead>Дети</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {families.data.map((family) => (
              <FamilyRow key={family.id} family={family} />
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
